"""Transactional POS extension; additive tables preserve v0.4 data."""
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from typing import Literal
import datetime as dt
import hashlib
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func, update, text
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy import String, Integer, ForeignKey, Text
from fastapi import Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from .main import (app, Base, engine, db, Product, Batch, Branch, Customer, Sale,
    SaleItem, SalesReturn, StockMove, Audit, JournalEntry, PharmacySetting,
    current_user, allowed, add_move, page, PERM_PREFIX)
from .pharmacy_core_v07 import DrugProfile, DispensingPolicy, CustomerDiscount, product_meta

class Offer(Base):
    __tablename__='pos_offers'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120))
    product_id:Mapped[int]=mapped_column(ForeignKey('products.id'))
    min_qty:Mapped[int]=mapped_column(Integer)
    percent:Mapped[str]=mapped_column(String(20))
    active:Mapped[int]=mapped_column(Integer,default=1)

class SaleTotals(Base):
    __tablename__='pos_sale_totals'
    sale_id:Mapped[int]=mapped_column(ForeignKey('sales.id'),primary_key=True)
    request_key:Mapped[str]=mapped_column(String(80),unique=True)
    request_hash:Mapped[str]=mapped_column(String(64))
    user_id:Mapped[int]=mapped_column(Integer)
    subtotal:Mapped[int]=mapped_column(Integer)
    discount:Mapped[int]=mapped_column(Integer)
    tax:Mapped[int]=mapped_column(Integer)
    total:Mapped[int]=mapped_column(Integer)
    tax_pct:Mapped[str]=mapped_column(String(20))
    snapshot:Mapped[str]=mapped_column(Text)

class ItemAmounts(Base):
    __tablename__='pos_item_amounts'
    item_id:Mapped[int]=mapped_column(ForeignKey('sale_items.id'),primary_key=True)
    cost:Mapped[int]=mapped_column(Integer)
    net:Mapped[int]=mapped_column(Integer)
    tax:Mapped[int]=mapped_column(Integer)

class Payment(Base):
    __tablename__='pos_payments'
    id:Mapped[int]=mapped_column(primary_key=True)
    sale_id:Mapped[int]=mapped_column(ForeignKey('sales.id'))
    method:Mapped[str]=mapped_column(String(20))
    amount:Mapped[int]=mapped_column(Integer)

Base.metadata.create_all(engine)
PERM_PREFIX.update({'/api/pos':'pos','/api/products':'pos','/receipt':'pos','/offers':'users'})

class Line(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_id:int=Field(gt=0,strict=True)
    qty:int=Field(gt=0,le=100000,strict=True)
    discount_pct:Decimal=Field(default=Decimal(0),ge=0,le=100,decimal_places=2)

class Tender(BaseModel):
    model_config=ConfigDict(extra='forbid')
    method:Literal['cash','card','wallet','bank']
    amount:Decimal=Field(gt=0,max_digits=12,decimal_places=2)

class Cart(BaseModel):
    model_config=ConfigDict(extra='forbid')
    branch_id:int=Field(gt=0,strict=True)
    customer_id:int|None=None
    items:list[Line]=Field(min_length=1,max_length=100)
    discount_amount:Decimal=Field(default=Decimal(0),ge=0,max_digits=12,decimal_places=2)
    payments:list[Tender]=Field(default_factory=list,max_length=4)
    request_key:str=Field(min_length=16,max_length=80)
    prescription_ref:str=Field(default='',max_length=120)
    prescriber_name:str=Field(default='',max_length=160)

D=Decimal

def cents(v):
    n=D(str(v))
    if not n.is_finite() or n<0 or n>D('1000000000'):
        raise HTTPException(400,'قيمة مالية غير صحيحة')
    return int((n*100).quantize(D(1),rounding=ROUND_HALF_UP))

def split(amount,weights):
    """Largest remainder allocation, conserving every cent."""
    total=sum(weights)
    if not total:return [0]*len(weights)
    parts=[amount*w//total for w in weights]
    order=sorted(range(len(weights)),key=lambda i:amount*weights[i]%total,reverse=True)
    for i in order[:amount-sum(parts)]:parts[i]+=1
    return parts

def actor(request,s,branch_id):
    u=current_user(request,s)
    if not u or not allowed(s,u,'pos'):raise HTTPException(403,'غير مسموح')
    if not allowed(s,u,'users') and u.branch_id!=branch_id:
        raise HTTPException(403,'الفرع غير مسموح')
    return u

def quote(cart,s):
    branch=s.get(Branch,cart.branch_id)
    if not branch or not branch.active:raise HTTPException(400,'الفرع غير متاح')
    if cart.customer_id is not None and not s.get(Customer,cart.customer_id):
        raise HTTPException(400,'العميل غير موجود')
    ids=[x.product_id for x in cart.items]
    if len(set(ids))!=len(ids):raise HTTPException(400,'ادمج الصنف المتكرر في سطر واحد')
    settings={x.key:x.value for x in s.scalars(select(PharmacySetting))}
    try:tax_pct=D(settings.get('tax_pct','0'))
    except Exception:raise HTTPException(400,'نسبة الضريبة في الإعدادات غير صحيحة')
    if not tax_pct.is_finite() or not 0<=tax_pct<=100:raise HTTPException(400,'نسبة الضريبة غير صحيحة')
    lines=[]
    for item in cart.items:
        p=s.get(Product,item.product_id)
        if not p:raise HTTPException(400,'الصنف غير موجود')
        pol=s.get(DispensingPolicy,p.id)
        if pol and pol.max_qty and item.qty>pol.max_qty:raise HTTPException(400,f'{p.trade_name}: أقصى كمية للصرف {pol.max_qty}')
        if pol and (pol.prescription_required or pol.level in ('rx','restricted','controlled')) and not cart.prescription_ref.strip():raise HTTPException(400,f'{p.trade_name}: يتطلب بيانات الروشتة/مرجع الصرف')
        available=s.scalar(select(func.coalesce(func.sum(Batch.qty),0)).where(Batch.product_id==p.id,Batch.branch_id==cart.branch_id,Batch.qty>0,Batch.expiry>dt.date.today()))
        if available<item.qty:raise HTTPException(409,f'{p.trade_name}: المتاح {available}')
        offers=s.scalars(select(Offer).where(Offer.product_id==p.id,Offer.active==1,Offer.min_qty<=item.qty)).all()
        offer=max(offers,key=lambda o:D(o.percent),default=None)
        cd=s.get(CustomerDiscount,cart.customer_id) if cart.customer_id else None
        customer_pct=D(cd.percent) if cd and cd.active else D(0)
        percent=max(item.discount_pct,D(offer.percent) if offer else D(0),customer_pct)
        gross=cents(p.sale_price)*item.qty
        discount=int((D(gross)*percent/100).quantize(D(1),rounding=ROUND_HALF_UP))
        lines.append(dict(product_id=p.id,name=p.trade_name,qty=item.qty,unit_price=cents(p.sale_price),gross=gross,discount=discount,net=gross-discount,offer=offer.name if offer and D(offer.percent)>=item.discount_pct else '',discount_pct=str(percent)))
    extra=cents(cart.discount_amount)
    if extra>sum(x['net'] for x in lines):raise HTTPException(400,'خصم الفاتورة أكبر من قيمتها')
    for line,part in zip(lines,split(extra,[x['net'] for x in lines])):
        line['discount']+=part;line['net']-=part
        line['tax']=int((D(line['net'])*tax_pct/100).quantize(D(1),rounding=ROUND_HALF_UP))
        line['total']=line['net']+line['tax']
    return dict(lines=lines,subtotal=sum(x['gross'] for x in lines),discount=sum(x['discount'] for x in lines),tax=sum(x['tax'] for x in lines),total=sum(x['total'] for x in lines),tax_pct=str(tax_pct),currency=settings.get('currency','EGP'),pharmacy_name=settings.get('pharmacy_name','eg4hosting pharmacy POS'),receipt_footer=settings.get('receipt_footer','شكراً لزيارتكم'))

@app.post('/api/pos/quote')
def cart_quote(cart:Cart,request:Request,s:Session=Depends(db)):
    actor(request,s,cart.branch_id)
    return quote(cart,s)

@app.post('/api/pos/checkout')
def checkout(cart:Cart,request:Request,s:Session=Depends(db)):
    # SQLite serializes competing writers before any stock reads.
    if engine.dialect.name=='sqlite':s.execute(text('BEGIN IMMEDIATE'))
    try:
        u=actor(request,s,cart.branch_id)
        digest=hashlib.sha256(cart.model_dump_json().encode()).hexdigest()
        prior=s.scalar(select(SaleTotals).where(SaleTotals.request_key==cart.request_key))
        if prior:
            if prior.request_hash!=digest or prior.user_id!=u.id:raise HTTPException(409,'مفتاح العملية مستخدم لطلب مختلف')
            return {'sale_id':prior.sale_id,'receipt':f'/receipt/{prior.sale_id}','total':prior.total,'replayed':True}
        q=quote(cart,s)
        if len({p.method for p in cart.payments})!=len(cart.payments):raise HTTPException(400,'طريقة الدفع مكررة')
        if sum(cents(p.amount) for p in cart.payments)!=q['total']:raise HTTPException(400,'مجموع المدفوعات يجب أن يساوي الإجمالي')
        sale=Sale(branch_id=cart.branch_id,customer_id=cart.customer_id,total=q['total']/100,payment=cart.payments[0].method if len(cart.payments)==1 else 'split')
        s.add(sale);s.flush()
        cost_total=0
        for line in q['lines']:
            batches=s.scalars(select(Batch).where(Batch.branch_id==cart.branch_id,Batch.product_id==line['product_id'],Batch.qty>0,Batch.expiry>dt.date.today()).order_by(Batch.expiry,Batch.id).with_for_update()).all()
            remaining=line['qty'];alloc=[]
            for b in batches:
                take=min(remaining,b.qty)
                if take:alloc.append((b,take));remaining-=take
                if not remaining:break
            if remaining:raise HTTPException(409,'تغير المخزون؛ أعد المحاولة')
            nets=split(line['net'],[n for _,n in alloc]);taxes=split(line['tax'],[n for _,n in alloc])
            for (b,n),net,tax in zip(alloc,nets,taxes):
                result=s.execute(update(Batch).where(Batch.id==b.id,Batch.qty>=n).values(qty=Batch.qty-n).execution_options(synchronize_session=False))
                if result.rowcount!=1:raise HTTPException(409,'تغير المخزون؛ أعد المحاولة')
                item=SaleItem(sale_id=sale.id,product_id=line['product_id'],batch_id=b.id,qty=n,unit_price=line['unit_price']/100)
                s.add(item);s.flush();s.add(ItemAmounts(item_id=item.id,net=net,tax=tax,cost=cents(b.cost)*n))
                add_move(s,cart.branch_id,line['product_id'],b.id,-n,'SALE',str(sale.id))
                cost_total+=cents(b.cost)*n
        s.add(SaleTotals(sale_id=sale.id,request_key=cart.request_key,request_hash=digest,user_id=u.id,subtotal=q['subtotal'],discount=q['discount'],tax=q['tax'],total=q['total'],tax_pct=q['tax_pct'],snapshot=json.dumps(q,ensure_ascii=False)))
        ref=f'SALE-{sale.id}'
        def journal(account,debit=0,credit=0):s.add(JournalEntry(branch_id=cart.branch_id,account=account,debit=debit/100,credit=credit/100,ref=ref))
        for p in cart.payments:
            amount=cents(p.amount);s.add(Payment(sale_id=sale.id,method=p.method,amount=amount));journal({'cash':'Cash','card':'Card Clearing','wallet':'Wallet Clearing','bank':'Bank'}[p.method],debit=amount)
        journal('Sales',credit=q['subtotal']-q['discount']);journal('Tax Payable',credit=q['tax'])
        journal('Cost of Goods Sold',debit=cost_total);journal('Inventory',credit=cost_total)
        s.add(Audit(action='SALE',details=f'sale={sale.id} user={u.username} total={q["total"]} cents'))
        s.commit()
        return {'sale_id':sale.id,'receipt':f'/receipt/{sale.id}','total':q['total'],'replayed':False}
    except Exception:
        s.rollback();raise

def load_pos_template():
    try:
        return Path(__file__).with_name('pos.html').read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        from .pos_template import POS_HTML
        return POS_HTML

@app.get('/pos',response_class=HTMLResponse)
def pos(request:Request,s:Session=Depends(db)):
    u=current_user(request,s)
    branches=s.scalars(select(Branch).where(Branch.active==1)).all()
    bo=''.join(f'<option value="{b.id}">{escape(b.name)}</option>' for b in branches if allowed(s,u,'users') or b.id==u.branch_id)
    co='<option value="">عميل نقدي</option>'+''.join(f'<option value="{c.id}">{escape(c.name)}</option>' for c in s.scalars(select(Customer)))
    sales=select(Sale).order_by(Sale.id.desc()).limit(20)
    if not allowed(s,u,'users'):sales=sales.where(Sale.branch_id==u.branch_id)
    recent=''.join(f'<tr><td><a href="/receipt/{x.id}">#{x.id}</a></td><td>{x.total:.2f}</td><td>{escape(x.payment)}</td></tr>' for x in s.scalars(sales))
    body=load_pos_template().replace('BRANCH_OPTIONS',bo).replace('CUSTOMER_OPTIONS',co).replace('RECENT_ROWS',recent)
    return page('نقطة البيع — سلة متعددة الأصناف',body)

@app.post('/pos')
def legacy_sale():
    raise HTTPException(400,'استخدم سلة البيع الجديدة /pos')

@app.get('/offers',response_class=HTMLResponse)
def offers(s:Session=Depends(db)):
    po=''.join(f'<option value="{p.id}">{escape(p.trade_name)}</option>' for p in s.scalars(select(Product)))
    rows=''.join(f'<tr><td>{escape(o.name)}</td><td>{escape(s.get(Product,o.product_id).trade_name)}</td><td>{o.min_qty}</td><td>{o.percent}%</td><td>{"نشط" if o.active else "متوقف"}</td><td><form method="post" action="/offers/{o.id}/toggle"><button>تفعيل / إيقاف</button></form></td></tr>' for o in s.scalars(select(Offer)))
    return page('عروض الكمية',f'<p>يطبق أعلى خصم بين عرض الكمية وخصم الصنف، ثم خصم الفاتورة، ثم الضريبة.</p><form method="post"><input name="name" placeholder="اسم العرض" required maxlength="120"><select name="product_id">{po}</select><label>أقل كمية <input name="min_qty" type="number" min="1" value="2" required></label><label>خصم % <input name="percent" type="number" min="0" max="100" step="0.01" required></label><button>إضافة عرض</button></form><table><tr><th>العرض</th><th>الصنف</th><th>الكمية</th><th>الخصم</th><th>الحالة</th><th></th></tr>{rows}</table>')

@app.post('/offers')
def offer_add(name:str=Form(...),product_id:int=Form(...),min_qty:int=Form(...),percent:Decimal=Form(...),s:Session=Depends(db)):
    if not name.strip() or len(name)>120 or not s.get(Product,product_id) or min_qty<1 or not percent.is_finite() or not 0<=percent<=100:raise HTTPException(400,'بيانات العرض غير صحيحة')
    s.add(Offer(name=name.strip(),product_id=product_id,min_qty=min_qty,percent=str(percent)))
    s.add(Audit(action='OFFER_ADD',details=name));s.commit();return RedirectResponse('/offers',303)

@app.post('/offers/{offer_id}/toggle')
def offer_toggle(offer_id:int,s:Session=Depends(db)):
    o=s.get(Offer,offer_id)
    if not o:raise HTTPException(404,'العرض غير موجود')
    o.active=1-o.active;s.add(Audit(action='OFFER_TOGGLE',details=str(o.id)));s.commit();return RedirectResponse('/offers',303)

@app.get('/receipt/{sale_id}',response_class=HTMLResponse)
def receipt(sale_id:int,request:Request,s:Session=Depends(db)):
    sale=s.get(Sale,sale_id)
    if not sale:raise HTTPException(404,'الفاتورة غير موجودة')
    actor(request,s,sale.branch_id)
    totals=s.get(SaleTotals,sale_id)
    if totals:
        q=json.loads(totals.snapshot)
        rows=''.join(f'<tr><td>{escape(x["name"])}</td><td>{x["qty"]}</td><td>{x["gross"]/100:.2f}</td><td>{x["discount"]/100:.2f}</td><td>{x["total"]/100:.2f}</td></tr>' for x in q['lines'])
        summary=f'قبل الخصم: {q["subtotal"]/100:.2f}<br>الخصم: {q["discount"]/100:.2f}<br>الضريبة ({q["tax_pct"]}%): {q["tax"]/100:.2f}'
    else:
        q={x.key:x.value for x in s.scalars(select(PharmacySetting))}
        rows=''.join(f'<tr><td>{escape(p.trade_name)}</td><td>{i.qty}</td><td>{i.qty*i.unit_price:.2f}</td><td>0.00</td><td>{i.qty*i.unit_price:.2f}</td></tr>' for i,p in s.execute(select(SaleItem,Product).join(Product,Product.id==SaleItem.product_id).where(SaleItem.sale_id==sale_id)))
        summary='فاتورة سابقة لـ v0.5'
    payments=''.join(f'<p>{escape(p.method)}: {p.amount/100:.2f}</p>' for p in s.scalars(select(Payment).where(Payment.sale_id==sale_id)))
    returned=s.scalar(select(func.coalesce(func.sum(SalesReturn.amount),0)).where(SalesReturn.sale_id==sale_id))
    st={x.key:x.value for x in s.scalars(select(PharmacySetting)).all()}; width=st.get('receipt_width','80'); logo=(f'<img src="{st.get("logo_data")}" style="max-width:42mm;max-height:22mm">' if st.get('logo_data') and st.get('show_logo','1')=='1' else ''); info=''; info += (f'<div>{escape(st.get("address",""))}</div>' if st.get('address') and st.get('show_address','1')=='1' else ''); info += (f'<div>{escape(st.get("phone",""))}</div>' if st.get('phone') and st.get('show_phone','1')=='1' else ''); info += (f'<div>Tax ID: {escape(st.get("tax_id",""))}</div>' if st.get('tax_id') and st.get('show_tax','1')=='1' else ''); return HTMLResponse(f'<!doctype html><html dir="rtl" lang="ar"><meta charset="utf-8"><title>Receipt {sale.id}</title><style>body{{font:12px Tahoma;width:{width}mm;margin:auto;text-align:center}}table{{text-align:right}}table{{width:100%;border-collapse:collapse}}td,th{{padding:4px;border-bottom:1px dashed}}@media print{{button,a{{display:none}}}}@page{{margin:3mm}}</style>{logo}<h2>{escape(q.get("pharmacy_name","eg4hosting pharmacy POS"))}</h2>{info}<p>فاتورة #{sale.id} — {sale.created_at:%Y-%m-%d %H:%M}</p><table><tr><th>الصنف</th><th>ك</th><th>قيمة</th><th>خصم</th><th>شامل الضريبة</th></tr>{rows}</table><p>{summary}</p><h3>الإجمالي: {sale.total:.2f} {escape(q.get("currency","EGP"))}</h3>{payments}<p>المرتجع: {returned:.2f}</p><p>{escape(q.get("receipt_footer","شكراً لزيارتكم"))}</p><button onclick="print()">طباعة</button> <a href="/pos">بيع جديد</a></html>')

@app.post('/returns/sale')
def return_sale(request:Request,sale_item_id:int=Form(...),qty:int=Form(...),reason:str=Form(''),s:Session=Depends(db)):
    if engine.dialect.name=='sqlite':s.execute(text('BEGIN IMMEDIATE'))
    i=s.get(SaleItem,sale_item_id)
    if not i:raise HTTPException(404,'الصنف غير موجود بالفاتورة')
    sale=s.get(Sale,i.sale_id)
    u=current_user(request,s)
    if not allowed(s,u,'users') and u.branch_id!=sale.branch_id:raise HTTPException(403,'الفرع غير مسموح')
    already=s.scalar(select(func.coalesce(func.sum(SalesReturn.qty),0)).where(SalesReturn.sale_item_id==i.id))
    if qty<1 or qty>i.qty-already:raise HTTPException(400,'كمية المرتجع غير صحيحة')
    amounts=s.get(ItemAmounts,i.id)
    # Cumulative rounding ensures partial refunds sum exactly to the paid line.
    def portion(n):return int((D(n)*D(already+qty)/i.qty).quantize(D(1),rounding=ROUND_HALF_UP))-int((D(n)*D(already)/i.qty).quantize(D(1),rounding=ROUND_HALF_UP))
    net=portion(amounts.net) if amounts else cents(i.unit_price)*qty
    tax=portion(amounts.tax) if amounts else 0
    amount=net+tax
    s.execute(update(Batch).where(Batch.id==i.batch_id).values(qty=Batch.qty+qty))
    s.add(SalesReturn(sale_id=sale.id,sale_item_id=i.id,branch_id=sale.branch_id,qty=qty,amount=amount/100,reason=reason))
    add_move(s,sale.branch_id,i.product_id,i.batch_id,qty,'SALE_RETURN',str(sale.id),reason)
    for account,debit,credit in [('Sales Returns',net,0),('Tax Payable',tax,0),('Refunds Payable',0,amount)]:
        s.add(JournalEntry(branch_id=sale.branch_id,account=account,debit=debit/100,credit=credit/100,ref=f'SR-{sale.id}'))
    if amounts:
        cost=portion(amounts.cost)
        s.add(JournalEntry(branch_id=sale.branch_id,account='Inventory',debit=cost/100,credit=0,ref=f'SR-{sale.id}'))
        s.add(JournalEntry(branch_id=sale.branch_id,account='Cost of Goods Sold',debit=0,credit=cost/100,ref=f'SR-{sale.id}'))
    s.add(Audit(action='SALE_RETURN',details=f'sale={sale.id} qty={qty} refund_due={amount} cents'))
    s.commit();return RedirectResponse('/returns',303)
