import os, shutil, datetime as dt, uuid, hashlib, secrets
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, String, Integer, Float, Date, DateTime, ForeignKey, Text, select, func, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

DB_URL=os.getenv('DB_URL','sqlite:///./data/pharmacy.db')
engine=create_engine(DB_URL, connect_args={'check_same_thread':False} if DB_URL.startswith('sqlite') else {})
class Base(DeclarativeBase): pass
class Branch(Base):
    __tablename__='branches'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(120)); code:Mapped[str]=mapped_column(String(30),unique=True); active:Mapped[int]=mapped_column(Integer,default=1)
class Product(Base):
    __tablename__='products'; id:Mapped[int]=mapped_column(primary_key=True); barcode:Mapped[str]=mapped_column(String(64),unique=True); trade_name:Mapped[str]=mapped_column(String(160)); active_ingredient:Mapped[str]=mapped_column(String(160),default=''); strength:Mapped[str]=mapped_column(String(80),default=''); dosage_form:Mapped[str]=mapped_column(String(80),default=''); manufacturer:Mapped[str]=mapped_column(String(120),default=''); sale_price:Mapped[float]=mapped_column(Float,default=0); reorder_level:Mapped[int]=mapped_column(Integer,default=5)
class Supplier(Base):
    __tablename__='suppliers'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(160)); phone:Mapped[str]=mapped_column(String(60),default=''); balance:Mapped[float]=mapped_column(Float,default=0)
class Customer(Base):
    __tablename__='customers'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(160)); phone:Mapped[str]=mapped_column(String(60),default='')
class Batch(Base):
    __tablename__='batches'; __table_args__=(UniqueConstraint('branch_id','product_id','batch_no',name='uq_batch_branch_product_no'),); id:Mapped[int]=mapped_column(primary_key=True); product_id:Mapped[int]=mapped_column(ForeignKey('products.id')); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); batch_no:Mapped[str]=mapped_column(String(80)); expiry:Mapped[dt.date]=mapped_column(Date); qty:Mapped[int]=mapped_column(Integer,default=0); cost:Mapped[float]=mapped_column(Float,default=0)
class StockMove(Base):
    __tablename__='stock_moves'; id:Mapped[int]=mapped_column(primary_key=True); event_id:Mapped[str]=mapped_column(String(36),unique=True,default=lambda:str(uuid.uuid4())); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); product_id:Mapped[int]=mapped_column(ForeignKey('products.id')); batch_id:Mapped[Optional[int]]=mapped_column(ForeignKey('batches.id'),nullable=True); qty_delta:Mapped[int]=mapped_column(Integer); reason:Mapped[str]=mapped_column(String(40)); ref:Mapped[str]=mapped_column(String(80),default=''); note:Mapped[str]=mapped_column(Text,default=''); prev_hash:Mapped[str]=mapped_column(String(64),default=''); event_hash:Mapped[str]=mapped_column(String(64),default=''); sync_state:Mapped[str]=mapped_column(String(20),default='pending')
class Sale(Base):
    __tablename__='sales'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); customer_id:Mapped[Optional[int]]=mapped_column(ForeignKey('customers.id'),nullable=True); total:Mapped[float]=mapped_column(Float,default=0); payment:Mapped[str]=mapped_column(String(30),default='cash')
class SaleItem(Base):
    __tablename__='sale_items'; id:Mapped[int]=mapped_column(primary_key=True); sale_id:Mapped[int]=mapped_column(ForeignKey('sales.id')); product_id:Mapped[int]=mapped_column(ForeignKey('products.id')); batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id')); qty:Mapped[int]=mapped_column(Integer); unit_price:Mapped[float]=mapped_column(Float)
class Purchase(Base):
    __tablename__='purchases'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); supplier_id:Mapped[int]=mapped_column(ForeignKey('suppliers.id')); invoice_no:Mapped[str]=mapped_column(String(80)); total:Mapped[float]=mapped_column(Float,default=0)
class Transfer(Base):
    __tablename__='transfers'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); from_branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); to_branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); product_id:Mapped[int]=mapped_column(ForeignKey('products.id')); source_batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id')); qty:Mapped[int]=mapped_column(Integer); status:Mapped[str]=mapped_column(String(20),default='received'); ref:Mapped[str]=mapped_column(String(80),default='')
class StockCount(Base):
    __tablename__='stock_counts'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id')); system_qty:Mapped[int]=mapped_column(Integer); physical_qty:Mapped[int]=mapped_column(Integer); variance:Mapped[int]=mapped_column(Integer); note:Mapped[str]=mapped_column(Text,default='')
class Audit(Base):
    __tablename__='audit'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); action:Mapped[str]=mapped_column(String(80)); details:Mapped[str]=mapped_column(Text,default='')
class Role(Base):
    __tablename__='roles'; id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(80),unique=True); permissions:Mapped[str]=mapped_column(Text,default='')
class User(Base):
    __tablename__='users'; id:Mapped[int]=mapped_column(primary_key=True); username:Mapped[str]=mapped_column(String(80),unique=True); display_name:Mapped[str]=mapped_column(String(120),default=''); password_hash:Mapped[str]=mapped_column(String(180)); role_id:Mapped[int]=mapped_column(ForeignKey('roles.id')); branch_id:Mapped[Optional[int]]=mapped_column(ForeignKey('branches.id'),nullable=True); active:Mapped[int]=mapped_column(Integer,default=1); session_token:Mapped[str]=mapped_column(String(80),default='')
class CashShift(Base):
    __tablename__='cash_shifts'; id:Mapped[int]=mapped_column(primary_key=True); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); opened_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); closed_at:Mapped[Optional[dt.datetime]]=mapped_column(DateTime,nullable=True); opening_cash:Mapped[float]=mapped_column(Float,default=0); closing_cash:Mapped[float]=mapped_column(Float,default=0); status:Mapped[str]=mapped_column(String(20),default='open')
class SupplierTxn(Base):
    __tablename__='supplier_txns'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); supplier_id:Mapped[int]=mapped_column(ForeignKey('suppliers.id')); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); kind:Mapped[str]=mapped_column(String(30)); amount:Mapped[float]=mapped_column(Float); ref:Mapped[str]=mapped_column(String(80),default=''); note:Mapped[str]=mapped_column(Text,default='')
class SalesReturn(Base):
    __tablename__='sales_returns'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); sale_id:Mapped[int]=mapped_column(ForeignKey('sales.id')); sale_item_id:Mapped[int]=mapped_column(ForeignKey('sale_items.id')); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); qty:Mapped[int]=mapped_column(Integer); amount:Mapped[float]=mapped_column(Float); reason:Mapped[str]=mapped_column(String(180),default='')
class PurchaseReturn(Base):
    __tablename__='purchase_returns'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); purchase_id:Mapped[int]=mapped_column(ForeignKey('purchases.id')); supplier_id:Mapped[int]=mapped_column(ForeignKey('suppliers.id')); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id')); qty:Mapped[int]=mapped_column(Integer); amount:Mapped[float]=mapped_column(Float); reason:Mapped[str]=mapped_column(String(180),default='')
class JournalEntry(Base):
    __tablename__='journal_entries'; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); branch_id:Mapped[int]=mapped_column(ForeignKey('branches.id')); account:Mapped[str]=mapped_column(String(80)); debit:Mapped[float]=mapped_column(Float,default=0); credit:Mapped[float]=mapped_column(Float,default=0); ref:Mapped[str]=mapped_column(String(80),default=''); memo:Mapped[str]=mapped_column(Text,default='')

class PharmacySetting(Base):
    __tablename__="pharmacy_settings"; id:Mapped[int]=mapped_column(primary_key=True); key:Mapped[str]=mapped_column(String(80),unique=True); value:Mapped[str]=mapped_column(Text,default="")
class DrugAlternative(Base):
    __tablename__="drug_alternatives"; id:Mapped[int]=mapped_column(primary_key=True); product_id:Mapped[int]=mapped_column(ForeignKey("products.id")); alternative_product_id:Mapped[int]=mapped_column(ForeignKey("products.id")); note:Mapped[str]=mapped_column(String(180),default="")
class Prescription(Base):
    __tablename__="prescriptions"; id:Mapped[int]=mapped_column(primary_key=True); created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow); customer_id:Mapped[int]=mapped_column(ForeignKey("customers.id")); doctor_name:Mapped[str]=mapped_column(String(160),default=""); notes:Mapped[str]=mapped_column(Text,default="")
class PrescriptionItem(Base):
    __tablename__="prescription_items"; id:Mapped[int]=mapped_column(primary_key=True); prescription_id:Mapped[int]=mapped_column(ForeignKey("prescriptions.id")); product_id:Mapped[int]=mapped_column(ForeignKey("products.id")); dosage:Mapped[str]=mapped_column(String(160),default=""); qty:Mapped[int]=mapped_column(Integer,default=1)

Base.metadata.create_all(engine)
def db():
    with Session(engine) as s: yield s

def add_move(s,branch_id,product_id,batch_id,qty_delta,reason,ref='',note=''):
    prev=s.scalar(select(StockMove.event_hash).order_by(StockMove.id.desc()).limit(1)) or ''
    event_id=str(uuid.uuid4()); raw=f'{event_id}|{branch_id}|{product_id}|{batch_id}|{qty_delta}|{reason}|{ref}|{prev}'
    h=hashlib.sha256(raw.encode()).hexdigest()
    m=StockMove(event_id=event_id,branch_id=branch_id,product_id=product_id,batch_id=batch_id,qty_delta=qty_delta,reason=reason,ref=ref,note=note,prev_hash=prev,event_hash=h,sync_state='pending'); s.add(m); return m

def seed():
    with Session(engine) as s:
        if not s.scalar(select(func.count()).select_from(Branch)):
            main=Branch(name='الفرع الرئيسي',code='MAIN'); b2=Branch(name='فرع تجريبي 2',code='B02'); s.add_all([main,b2]); s.flush()
            ps=[Product(barcode='622100000001',trade_name='Augmentin 1g',active_ingredient='Amoxicillin/Clavulanate',strength='1 g',dosage_form='Tablets',manufacturer='Demo Pharma',sale_price=220,reorder_level=10),Product(barcode='622100000002',trade_name='Panadol Extra',active_ingredient='Paracetamol/Caffeine',strength='500/65 mg',dosage_form='Tablets',manufacturer='Demo Pharma',sale_price=55,reorder_level=20),Product(barcode='622100000003',trade_name='Vitamin C 1000',active_ingredient='Ascorbic Acid',strength='1000 mg',dosage_form='Tablets',manufacturer='Demo Pharma',sale_price=90,reorder_level=8)]
            s.add_all(ps); s.add_all([Supplier(name='مخزن تجريبي',phone='01000000000'),Customer(name='عميل نقدي')]); s.flush()
            for i,p in enumerate(ps):
                b=Batch(product_id=p.id,branch_id=main.id,batch_no=f'DEMO-{i+1}',expiry=dt.date.today()+dt.timedelta(days=180+i*120),qty=30+i*10,cost=p.sale_price*.72); s.add(b); s.flush(); add_move(s,main.id,p.id,b.id,b.qty,'OPENING','SEED')
            s.add(Audit(action='SEED',details='Initial multi-branch demo data created')); s.commit()
seed()

def password_hash(password):
    salt=secrets.token_hex(16); dk=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),200000).hex(); return salt+'$'+dk
def password_ok(password,stored):
    try:
        salt,want=stored.split('$',1); got=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),200000).hex(); return secrets.compare_digest(got,want)
    except Exception: return False
def seed_security():
    with Session(engine) as s:
        if not s.scalar(select(func.count()).select_from(Role)):
            admin=Role(name='Admin',permissions='*'); pharmacist=Role(name='Pharmacist',permissions='pos,inventory,returns'); accountant=Role(name='Accountant',permissions='suppliers,accounting,reports'); s.add_all([admin,pharmacist,accountant]); s.flush()
            main=s.scalar(select(Branch).order_by(Branch.id)); s.add(User(username='admin',display_name='System Admin',password_hash=password_hash(os.getenv('ADMIN_PASSWORD','admin123')),role_id=admin.id,branch_id=main.id if main else None)); s.commit()
seed_security()
app=FastAPI(title='eg4hosting pharmacy POS',version='1.1.3')
from .ui import CSS, render_page
def page(title,body):
    return render_page(title,body)
@app.get('/health')
def health(s:Session=Depends(db)):
    pending=s.scalar(select(func.count()).select_from(StockMove).where(StockMove.sync_state=='pending')); return {'status':'ok','version':'1.1.3','db':DB_URL.split(':')[0],'pending_sync_events':pending}
@app.get('/',response_class=HTMLResponse)
def home(s:Session=Depends(db)):
    products=s.scalar(select(func.count()).select_from(Product)); branches=s.scalar(select(func.count()).select_from(Branch)); stock=s.scalar(select(func.coalesce(func.sum(Batch.qty),0))); transfers=s.scalar(select(func.count()).select_from(Transfer)); pending=s.scalar(select(func.count()).select_from(StockMove).where(StockMove.sync_state=='pending')); exp=s.scalar(select(func.count()).select_from(Batch).where(Batch.expiry<=dt.date.today()+dt.timedelta(days=90)))
    return page('لوحة التحكم',f'<div class="grid"><div class="card"><div class="muted">الفروع</div><div class="kpi">{branches}</div></div><div class="card"><div class="muted">الأدوية</div><div class="kpi">{products}</div></div><div class="card"><div class="muted">الوحدات بالمخزون</div><div class="kpi">{stock}</div></div><div class="card"><div class="muted">التحويلات</div><div class="kpi">{transfers}</div></div><div class="card"><div class="muted">قرب انتهاء ≤90 يوم</div><div class="kpi">{exp}</div></div><div class="card"><div class="muted">Sync pending</div><div class="kpi">{pending}</div></div></div>')
@app.get('/branches',response_class=HTMLResponse)
def branches(s:Session=Depends(db)):
    rows=s.scalars(select(Branch).order_by(Branch.id)).all(); tr=''.join(f'<tr><td>{x.code}</td><td>{x.name}</td><td>{"نشط" if x.active else "موقوف"}</td></tr>' for x in rows); form='''<form method="post"><input name="code" placeholder="كود الفرع" required><input name="name" placeholder="اسم الفرع" required><button>إضافة فرع</button></form>'''; return page('الفروع',form+f'<table><tr><th>الكود</th><th>الاسم</th><th>الحالة</th></tr>{tr}</table>')
@app.post('/branches')
def add_branch(code:str=Form(...),name:str=Form(...),s:Session=Depends(db)):
    if s.scalar(select(Branch).where(Branch.code==code)): raise HTTPException(400,'كود الفرع مستخدم'); s.add(Branch(code=code,name=name)); s.add(Audit(action='BRANCH_ADD',details=f'{code} {name}')); s.commit(); return RedirectResponse('/branches',303)
@app.get('/products',response_class=HTMLResponse)
def products(q:str='',page_no:int=1,s:Session=Depends(db)):
    from .pharmacy_core_v07 import DrugProfile
    from sqlalchemy import or_
    page_no=max(1,page_no); per_page=50
    stmt=select(Product,DrugProfile).outerjoin(DrugProfile,DrugProfile.product_id==Product.id)
    count_stmt=select(func.count()).select_from(Product).outerjoin(DrugProfile,DrugProfile.product_id==Product.id)
    if q.strip():
        like=f'%{q.strip()}%'
        cond=or_(Product.trade_name.ilike(like),Product.active_ingredient.ilike(like),Product.barcode.ilike(like),Product.manufacturer.ilike(like),DrugProfile.arabic_name.ilike(like),DrugProfile.generic_name.ilike(like),DrugProfile.category.ilike(like))
        stmt=stmt.where(cond); count_stmt=count_stmt.where(cond)
    total=s.scalar(count_stmt) or 0
    pages=max(1,(total+per_page-1)//per_page); page_no=min(page_no,pages)
    rows=s.execute(stmt.order_by(Product.trade_name).offset((page_no-1)*per_page).limit(per_page)).all()
    tr=''.join(f'<tr><td>{i}</td><td>{d.arabic_name if d and d.arabic_name else "—"}</td><td><b>{p.trade_name}</b></td><td>{p.active_ingredient or "—"}</td><td>{p.manufacturer or "—"}</td><td>{d.category if d and d.category else "—"}</td><td>{p.dosage_form or "—"}</td><td>{p.sale_price:.2f}</td><td><a class="action" href="/drug-guide/{p.id}">التفاصيل</a><a class="action primary" href="/inventory/opening?product_id={p.id}">إضافة للمخزون</a></td></tr>' for i,(p,d) in enumerate(rows,(page_no-1)*per_page+1))
    from urllib.parse import quote_plus
    qq=quote_plus(q.strip())
    prev=f'<a class="action" href="/products?q={qq}&page_no={page_no-1}">السابق</a>' if page_no>1 else ''
    nxt=f'<a class="action" href="/products?q={qq}&page_no={page_no+1}">التالي</a>' if page_no<pages else ''
    form=f'''<div class="grid"><div class="card"><div class="muted">إجمالي دليل الأدوية</div><div class="kpi">{total:,}</div></div><div class="card"><div class="muted">الصفحة</div><div class="kpi">{page_no} / {pages}</div></div></div><form method="get"><input name="q" value="{q}" placeholder="ابحث عربي / English / المادة الفعالة / الشركة / التصنيف" style="min-width:480px"><button>بحث</button><a class="action" href="/products">مسح البحث</a></form>'''
    nav=f'<div style="display:flex;gap:8px;align-items:center;margin-top:14px">{prev}<span class="pill">عرض {len(rows)} من {total:,}</span>{nxt}</div>'
    return page('دليل الأدوية المصري',form+f'<table><tr><th>#</th><th>الاسم العربي</th><th>English</th><th>المادة الفعالة</th><th>الشركة</th><th>التصنيف</th><th>طريقة الاستخدام</th><th>السعر EGP</th><th>إجراء</th></tr>{tr}</table>'+nav)
@app.post('/products')
def add_product(barcode:str=Form(...),trade_name:str=Form(...),active:str=Form(''),price:float=Form(...),s:Session=Depends(db)):
    s.add(Product(barcode=barcode,trade_name=trade_name,active_ingredient=active,sale_price=price)); s.add(Audit(action='PRODUCT_ADD',details=trade_name)); s.commit(); return RedirectResponse('/products',303)
@app.get('/inventory',response_class=HTMLResponse)
def inventory(s:Session=Depends(db)):
    rows=s.execute(select(Batch,Product,Branch).join(Product,Product.id==Batch.product_id).join(Branch,Branch.id==Batch.branch_id).order_by(Branch.code,Batch.expiry)).all(); tr=''.join(f'<tr><td>{br.code}</td><td>{p.trade_name}</td><td>{b.batch_no}</td><td>{b.qty}</td><td>{b.cost:.2f}</td><td>{b.expiry}</td></tr>' for b,p,br in rows); return page('المخزون / Batch / Expiry',f'<table><tr><th>الفرع</th><th>الصنف</th><th>Batch</th><th>الكمية</th><th>التكلفة</th><th>الصلاحية</th></tr>{tr}</table>')
@app.get('/pos',response_class=HTMLResponse)
def pos(s:Session=Depends(db)):
    po=''.join(f'<option value="{p.id}">{p.trade_name} - {p.sale_price:.2f}</option>' for p in s.scalars(select(Product)).all()); bo=''.join(f'<option value="{b.id}">{b.code} - {b.name}</option>' for b in s.scalars(select(Branch).where(Branch.active==1)).all()); sales=s.scalars(select(Sale).order_by(Sale.id.desc()).limit(20)).all(); tr=''.join(f'<tr><td>{x.id}</td><td>{x.branch_id}</td><td>{x.created_at:%Y-%m-%d %H:%M}</td><td>{x.total:.2f}</td></tr>' for x in sales); return page('المبيعات / POS',f'<div class="card"><form method="post"><select name="branch_id">{bo}</select><select name="product_id">{po}</select><input name="qty" type="number" min="1" value="1"><select name="payment"><option>cash</option><option>card</option><option>wallet</option></select><button>بيع FEFO</button></form></div><table><tr><th>#</th><th>فرع</th><th>التاريخ</th><th>الإجمالي</th></tr>{tr}</table>')
@app.post('/pos')
def make_sale(branch_id:int=Form(...),product_id:int=Form(...),qty:int=Form(...),payment:str=Form('cash'),s:Session=Depends(db)):
    p=s.get(Product,product_id); need=qty; batches=s.scalars(select(Batch).where(Batch.branch_id==branch_id,Batch.product_id==product_id,Batch.qty>0,Batch.expiry>dt.date.today()).order_by(Batch.expiry)).all(); available=sum(b.qty for b in batches)
    if not p or available<qty: raise HTTPException(400,f'الرصيد غير كاف. المتاح {available}')
    sale=Sale(branch_id=branch_id,total=p.sale_price*qty,payment=payment); s.add(sale); s.flush()
    for b in batches:
        if need<=0: break
        take=min(need,b.qty); b.qty-=take; need-=take; s.add(SaleItem(sale_id=sale.id,product_id=p.id,batch_id=b.id,qty=take,unit_price=p.sale_price)); add_move(s,branch_id,p.id,b.id,-take,'SALE',str(sale.id))
    s.add(Audit(action='SALE',details=f'{sale.id}: {p.trade_name} x{qty} branch={branch_id}')); s.commit(); return RedirectResponse('/pos',303)
@app.get('/purchases',response_class=HTMLResponse)
def purchases(s:Session=Depends(db)):
    po=''.join(f'<option value="{p.id}">{p.trade_name}</option>' for p in s.scalars(select(Product)).all()); so=''.join(f'<option value="{x.id}">{x.name}</option>' for x in s.scalars(select(Supplier)).all()); bo=''.join(f'<option value="{b.id}">{b.code}</option>' for b in s.scalars(select(Branch).where(Branch.active==1)).all()); form=f'''<div class="card"><form method="post"><select name="branch_id">{bo}</select><select name="supplier_id">{so}</select><select name="product_id">{po}</select><input name="invoice_no" placeholder="رقم الفاتورة" required><input name="batch_no" placeholder="Batch" required><input name="expiry" type="date" required><input name="qty" type="number" min="1" placeholder="الكمية" required><input name="cost" type="number" step="0.01" placeholder="التكلفة" required><button>استلام</button></form></div>'''; return page('المشتريات',form)
@app.post('/purchases')
def add_purchase(branch_id:int=Form(...),supplier_id:int=Form(...),product_id:int=Form(...),invoice_no:str=Form(...),batch_no:str=Form(...),expiry:dt.date=Form(...),qty:int=Form(...),cost:float=Form(...),s:Session=Depends(db)):
    pur=Purchase(branch_id=branch_id,supplier_id=supplier_id,invoice_no=invoice_no,total=qty*cost); s.add(pur); s.flush(); b=s.scalar(select(Batch).where(Batch.product_id==product_id,Batch.branch_id==branch_id,Batch.batch_no==batch_no))
    if b: b.qty+=qty; b.cost=cost; b.expiry=expiry
    else: b=Batch(product_id=product_id,branch_id=branch_id,batch_no=batch_no,expiry=expiry,qty=qty,cost=cost); s.add(b); s.flush()
    s.add(SupplierTxn(supplier_id=supplier_id,branch_id=branch_id,kind='PURCHASE',amount=pur.total,ref=str(pur.id))); sup=s.get(Supplier,supplier_id); sup.balance+=pur.total; s.add(JournalEntry(branch_id=branch_id,account='Inventory',debit=pur.total,credit=0,ref=f'PUR-{pur.id}')); s.add(JournalEntry(branch_id=branch_id,account='Accounts Payable',debit=0,credit=pur.total,ref=f'PUR-{pur.id}')); add_move(s,branch_id,product_id,b.id,qty,'PURCHASE',str(pur.id)); s.add(Audit(action='PURCHASE',details=f'{invoice_no} qty={qty} branch={branch_id}')); s.commit(); return RedirectResponse('/purchases',303)
@app.get('/transfers',response_class=HTMLResponse)
def transfers(s:Session=Depends(db)):
    branches=s.scalars(select(Branch).where(Branch.active==1)).all(); bo=''.join(f'<option value="{b.id}">{b.code}-{b.name}</option>' for b in branches); batches=s.execute(select(Batch,Product,Branch).join(Product).join(Branch).where(Batch.qty>0).order_by(Branch.code,Product.trade_name)).all(); bopt=''.join(f'<option value="{b.id}">{br.code} | {p.trade_name} | {b.batch_no} | Qty {b.qty}</option>' for b,p,br in batches); form=f'''<div class="card"><form method="post"><select name="source_batch_id">{bopt}</select><select name="to_branch_id">{bo}</select><input name="qty" type="number" min="1" placeholder="الكمية" required><button>تحويل واستلام</button></form></div>'''; rows=s.execute(select(Transfer,Product).join(Product).order_by(Transfer.id.desc()).limit(50)).all(); tr=''.join(f'<tr><td>{t.id}</td><td>{t.from_branch_id} → {t.to_branch_id}</td><td>{p.trade_name}</td><td>{t.qty}</td><td>{t.status}</td></tr>' for t,p in rows); return page('تحويلات الفروع',form+f'<table><tr><th>#</th><th>المسار</th><th>الصنف</th><th>الكمية</th><th>الحالة</th></tr>{tr}</table>')
@app.post('/transfers')
def do_transfer(source_batch_id:int=Form(...),to_branch_id:int=Form(...),qty:int=Form(...),s:Session=Depends(db)):
    src=s.get(Batch,source_batch_id)
    if not src or src.qty<qty: raise HTTPException(400,'الرصيد غير كاف للتحويل')
    if src.branch_id==to_branch_id: raise HTTPException(400,'لا يمكن التحويل لنفس الفرع')
    ref=f'TRF-{dt.datetime.utcnow():%Y%m%d%H%M%S}-{src.id}'; src.qty-=qty; dst=s.scalar(select(Batch).where(Batch.branch_id==to_branch_id,Batch.product_id==src.product_id,Batch.batch_no==src.batch_no))
    if dst: dst.qty+=qty; dst.expiry=src.expiry; dst.cost=src.cost
    else: dst=Batch(branch_id=to_branch_id,product_id=src.product_id,batch_no=src.batch_no,expiry=src.expiry,qty=qty,cost=src.cost); s.add(dst); s.flush()
    t=Transfer(from_branch_id=src.branch_id,to_branch_id=to_branch_id,product_id=src.product_id,source_batch_id=src.id,qty=qty,status='received',ref=ref); s.add(t); add_move(s,src.branch_id,src.product_id,src.id,-qty,'TRANSFER_OUT',ref); add_move(s,to_branch_id,src.product_id,dst.id,qty,'TRANSFER_IN',ref); s.add(Audit(action='TRANSFER',details=f'{ref} qty={qty}')); s.commit(); return RedirectResponse('/transfers',303)
@app.get('/counts',response_class=HTMLResponse)
def counts(s:Session=Depends(db)):
    batches=s.execute(select(Batch,Product,Branch).join(Product).join(Branch).order_by(Branch.code,Product.trade_name)).all(); opt=''.join(f'<option value="{b.id}">{br.code} | {p.trade_name} | {b.batch_no} | system={b.qty}</option>' for b,p,br in batches); form=f'''<div class="card"><form method="post"><select name="batch_id">{opt}</select><input name="physical_qty" type="number" min="0" placeholder="الكمية الفعلية" required><input name="note" placeholder="ملاحظة"><button>اعتماد الجرد</button></form></div>'''; rows=s.scalars(select(StockCount).order_by(StockCount.id.desc()).limit(50)).all(); tr=''.join(f'<tr><td>{x.id}</td><td>{x.branch_id}</td><td>{x.batch_id}</td><td>{x.system_qty}</td><td>{x.physical_qty}</td><td>{x.variance}</td></tr>' for x in rows); return page('الجرد والتسويات',form+f'<table><tr><th>#</th><th>فرع</th><th>Batch</th><th>System</th><th>Physical</th><th>Variance</th></tr>{tr}</table>')
@app.post('/counts')
def do_count(batch_id:int=Form(...),physical_qty:int=Form(...),note:str=Form(''),s:Session=Depends(db)):
    b=s.get(Batch,batch_id)
    if not b: raise HTTPException(404,'Batch غير موجود')
    system=b.qty; variance=physical_qty-system; c=StockCount(branch_id=b.branch_id,batch_id=b.id,system_qty=system,physical_qty=physical_qty,variance=variance,note=note); s.add(c); s.flush(); b.qty=physical_qty
    if variance: add_move(s,b.branch_id,b.product_id,b.id,variance,'STOCK_COUNT',str(c.id),note)
    s.add(Audit(action='STOCK_COUNT',details=f'count={c.id} variance={variance}')); s.commit(); return RedirectResponse('/counts',303)
@app.get('/ledger',response_class=HTMLResponse)
def ledger(s:Session=Depends(db)):
    rows=s.execute(select(StockMove,Product,Branch).join(Product).join(Branch).order_by(StockMove.id.desc()).limit(200)).all(); tr=''.join(f'<tr><td>{m.id}</td><td>{br.code}</td><td>{p.trade_name}</td><td>{m.qty_delta:+d}</td><td>{m.reason}</td><td>{m.ref}</td><td>{m.sync_state}</td><td><code>{m.event_hash[:10]}</code></td></tr>' for m,p,br in rows); return page('Stock Ledger / Sync Events',f'<table><tr><th>#</th><th>فرع</th><th>الصنف</th><th>Δ</th><th>السبب</th><th>Ref</th><th>Sync</th><th>Hash</th></tr>{tr}</table>')
@app.get('/reports',response_class=HTMLResponse)
def reports(s:Session=Depends(db)):
    low=s.execute(select(Branch,Product,func.coalesce(func.sum(Batch.qty),0).label('q')).join(Batch,Branch.id==Batch.branch_id).join(Product,Product.id==Batch.product_id).group_by(Branch.id,Product.id).having(func.coalesce(func.sum(Batch.qty),0)<=Product.reorder_level)).all(); lowtr=''.join(f'<tr><td>{br.code}</td><td>{p.trade_name}</td><td>{q}</td><td>{p.reorder_level}</td></tr>' for br,p,q in low); exp=s.execute(select(Batch,Product,Branch).join(Product).join(Branch).where(Batch.expiry<=dt.date.today()+dt.timedelta(days=180)).order_by(Batch.expiry)).all(); exptr=''.join(f'<tr><td>{br.code}</td><td>{p.trade_name}</td><td>{b.batch_no}</td><td>{b.qty}</td><td>{b.expiry}</td></tr>' for b,p,br in exp); return page('التقارير',f'<h2>إعادة الطلب حسب الفرع</h2><table><tr><th>الفرع</th><th>الصنف</th><th>الرصيد</th><th>Reorder</th></tr>{lowtr}</table><h2>الصلاحية خلال 180 يوم</h2><table><tr><th>الفرع</th><th>الصنف</th><th>Batch</th><th>Qty</th><th>Expiry</th></tr>{exptr}</table>')

@app.get('/users',response_class=HTMLResponse)
def users(s:Session=Depends(db)):
    roles=s.scalars(select(Role)).all(); ro=''.join(f'<option value="{r.id}">{r.name}</option>' for r in roles); br=''.join(f'<option value="{b.id}">{b.code}</option>' for b in s.scalars(select(Branch)).all()); rows=s.execute(select(User,Role).join(Role,Role.id==User.role_id)).all(); tr=''.join(f'<tr><td>{u.username}</td><td>{u.display_name}</td><td>{r.name}</td><td>{u.branch_id or "-"}</td><td>{"نشط" if u.active else "موقوف"}</td></tr>' for u,r in rows); return page('المستخدمون والصلاحيات',f'<div class="card"><form method="post"><input name="username" placeholder="Username" required><input name="display_name" placeholder="الاسم"><input name="password" type="password" placeholder="Password" required><select name="role_id">{ro}</select><select name="branch_id">{br}</select><button>إضافة مستخدم</button></form></div><table><tr><th>User</th><th>الاسم</th><th>Role</th><th>Branch</th><th>الحالة</th></tr>{tr}</table>')
@app.post('/users')
def add_user(username:str=Form(...),display_name:str=Form(''),password:str=Form(...),role_id:int=Form(...),branch_id:int=Form(...),s:Session=Depends(db)):
    if s.scalar(select(User).where(User.username==username)): raise HTTPException(400,'اسم المستخدم موجود')
    s.add(User(username=username,display_name=display_name,password_hash=password_hash(password),role_id=role_id,branch_id=branch_id)); s.add(Audit(action='USER_ADD',details=username)); s.commit(); return RedirectResponse('/users',303)
@app.get('/suppliers',response_class=HTMLResponse)
def supplier_accounts(s:Session=Depends(db)):
    rows=s.scalars(select(Supplier).order_by(Supplier.name)).all(); tr=''.join(f'<tr><td>{x.id}</td><td>{x.name}</td><td>{x.phone}</td><td>{x.balance:.2f}</td></tr>' for x in rows); so=''.join(f'<option value="{x.id}">{x.name}</option>' for x in rows); bo=''.join(f'<option value="{b.id}">{b.code}</option>' for b in s.scalars(select(Branch)).all()); return page('حسابات الموردين',f'<div class="card"><form method="post" action="/suppliers/pay"><select name="supplier_id">{so}</select><select name="branch_id">{bo}</select><input name="amount" type="number" step="0.01" min="0.01" placeholder="دفعة" required><input name="note" placeholder="ملاحظة"><button>تسجيل دفعة</button></form></div><table><tr><th>#</th><th>المورد</th><th>الهاتف</th><th>الرصيد المستحق</th></tr>{tr}</table>')
@app.post('/suppliers/pay')
def supplier_pay(supplier_id:int=Form(...),branch_id:int=Form(...),amount:float=Form(...),note:str=Form(''),s:Session=Depends(db)):
    sup=s.get(Supplier,supplier_id); sup.balance-=amount; s.add(SupplierTxn(supplier_id=supplier_id,branch_id=branch_id,kind='PAYMENT',amount=-amount,ref='PAY',note=note)); s.add(JournalEntry(branch_id=branch_id,account='Accounts Payable',debit=amount,credit=0,ref='SUP-PAY',memo=note)); s.add(JournalEntry(branch_id=branch_id,account='Cash',debit=0,credit=amount,ref='SUP-PAY',memo=note)); s.add(Audit(action='SUPPLIER_PAYMENT',details=f'{sup.name} {amount}')); s.commit(); return RedirectResponse('/suppliers',303)
@app.get('/shifts',response_class=HTMLResponse)
def shifts(s:Session=Depends(db)):
    bo=''.join(f'<option value="{b.id}">{b.code}-{b.name}</option>' for b in s.scalars(select(Branch)).all()); rows=s.scalars(select(CashShift).order_by(CashShift.id.desc()).limit(50)).all(); tr=''.join(f'<tr><td>{x.id}</td><td>{x.branch_id}</td><td>{x.opened_at:%Y-%m-%d %H:%M}</td><td>{x.status}</td><td>{x.opening_cash:.2f}</td><td>{x.closing_cash:.2f}</td><td>{f"<form method=post action=/shifts/{x.id}/close><input name=closing_cash type=number step=0.01 required><button>إغلاق</button></form>" if x.status=="open" else ""}</td></tr>' for x in rows); return page('ورديات الكاشير',f'<div class="card"><form method="post"><select name="branch_id">{bo}</select><input name="opening_cash" type="number" step="0.01" value="0"><button>فتح وردية</button></form></div><table><tr><th>#</th><th>فرع</th><th>فتح</th><th>الحالة</th><th>Opening</th><th>Closing</th><th></th></tr>{tr}</table>')
@app.post('/shifts')
def open_shift(branch_id:int=Form(...),opening_cash:float=Form(0),s:Session=Depends(db)):
    if s.scalar(select(CashShift).where(CashShift.branch_id==branch_id,CashShift.status=='open')): raise HTTPException(400,'يوجد وردية مفتوحة للفرع')
    s.add(CashShift(branch_id=branch_id,opening_cash=opening_cash)); s.add(Audit(action='SHIFT_OPEN',details=f'branch={branch_id}')); s.commit(); return RedirectResponse('/shifts',303)
@app.post('/shifts/{shift_id}/close')
def close_shift(shift_id:int,closing_cash:float=Form(...),s:Session=Depends(db)):
    x=s.get(CashShift,shift_id); x.status='closed'; x.closed_at=dt.datetime.utcnow(); x.closing_cash=closing_cash; s.add(Audit(action='SHIFT_CLOSE',details=f'{shift_id} closing={closing_cash}')); s.commit(); return RedirectResponse('/shifts',303)
@app.get('/returns',response_class=HTMLResponse)
def returns(s:Session=Depends(db)):
    items=s.execute(select(SaleItem,Sale,Product).join(Sale,Sale.id==SaleItem.sale_id).join(Product,Product.id==SaleItem.product_id).order_by(SaleItem.id.desc()).limit(100)).all(); io=''.join(f'<option value="{i.id}">Sale {sale.id} | {p.trade_name} | qty {i.qty}</option>' for i,sale,p in items); batches=s.execute(select(Batch,Product).join(Product).where(Batch.qty>0)).all(); bo=''.join(f'<option value="{b.id}">{p.trade_name} | {b.batch_no} | qty {b.qty}</option>' for b,p in batches); purs=s.scalars(select(Purchase).order_by(Purchase.id.desc()).limit(100)).all(); po=''.join(f'<option value="{x.id}">PUR {x.id} / {x.invoice_no}</option>' for x in purs); return page('المرتجعات',f'<div class="grid"><div class="card"><h3>مرتجع بيع</h3><form method="post" action="/returns/sale"><select name="sale_item_id">{io}</select><input name="qty" type="number" min="1" value="1"><input name="reason" placeholder="السبب"><button>اعتماد مرتجع البيع</button></form></div><div class="card"><h3>مرتجع مشتريات</h3><form method="post" action="/returns/purchase"><select name="purchase_id">{po}</select><select name="batch_id">{bo}</select><input name="qty" type="number" min="1" value="1"><input name="reason" placeholder="السبب"><button>اعتماد مرتجع المورد</button></form></div></div>')
@app.post('/returns/sale')
def sale_return(sale_item_id:int=Form(...),qty:int=Form(...),reason:str=Form(''),s:Session=Depends(db)):
    i=s.get(SaleItem,sale_item_id); sale=s.get(Sale,i.sale_id); b=s.get(Batch,i.batch_id); already=s.scalar(select(func.coalesce(func.sum(SalesReturn.qty),0)).where(SalesReturn.sale_item_id==i.id)) or 0
    if qty<1 or qty>i.qty-already: raise HTTPException(400,'كمية المرتجع غير صحيحة')
    amount=qty*i.unit_price; b.qty+=qty; s.add(SalesReturn(sale_id=sale.id,sale_item_id=i.id,branch_id=sale.branch_id,qty=qty,amount=amount,reason=reason)); add_move(s,sale.branch_id,i.product_id,b.id,qty,'SALE_RETURN',str(sale.id),reason); s.add(JournalEntry(branch_id=sale.branch_id,account='Sales Returns',debit=amount,credit=0,ref=f'SR-{sale.id}')); s.add(JournalEntry(branch_id=sale.branch_id,account='Cash/Receivable',debit=0,credit=amount,ref=f'SR-{sale.id}')); s.add(Audit(action='SALE_RETURN',details=f'sale={sale.id} qty={qty}')); s.commit(); return RedirectResponse('/returns',303)
@app.post('/returns/purchase')
def purchase_return(purchase_id:int=Form(...),batch_id:int=Form(...),qty:int=Form(...),reason:str=Form(''),s:Session=Depends(db)):
    pur=s.get(Purchase,purchase_id); b=s.get(Batch,batch_id)
    if not pur or not b or b.branch_id!=pur.branch_id or qty<1 or qty>b.qty: raise HTTPException(400,'بيانات المرتجع غير صحيحة')
    amount=qty*b.cost; b.qty-=qty; sup=s.get(Supplier,pur.supplier_id); sup.balance-=amount; s.add(PurchaseReturn(purchase_id=pur.id,supplier_id=pur.supplier_id,branch_id=pur.branch_id,batch_id=b.id,qty=qty,amount=amount,reason=reason)); s.add(SupplierTxn(supplier_id=pur.supplier_id,branch_id=pur.branch_id,kind='PURCHASE_RETURN',amount=-amount,ref=str(pur.id),note=reason)); add_move(s,pur.branch_id,b.product_id,b.id,-qty,'PURCHASE_RETURN',str(pur.id),reason); s.add(JournalEntry(branch_id=pur.branch_id,account='Accounts Payable',debit=amount,credit=0,ref=f'PR-{pur.id}')); s.add(JournalEntry(branch_id=pur.branch_id,account='Inventory',debit=0,credit=amount,ref=f'PR-{pur.id}')); s.add(Audit(action='PURCHASE_RETURN',details=f'pur={pur.id} qty={qty}')); s.commit(); return RedirectResponse('/returns',303)
@app.get('/accounting',response_class=HTMLResponse)
def accounting(s:Session=Depends(db)):
    rows=s.scalars(select(JournalEntry).order_by(JournalEntry.id.desc()).limit(200)).all(); tr=''.join(f'<tr><td>{x.created_at:%Y-%m-%d %H:%M}</td><td>{x.branch_id}</td><td>{x.account}</td><td>{x.debit:.2f}</td><td>{x.credit:.2f}</td><td>{x.ref}</td></tr>' for x in rows); debit=s.scalar(select(func.coalesce(func.sum(JournalEntry.debit),0))); credit=s.scalar(select(func.coalesce(func.sum(JournalEntry.credit),0))); return page('Accounting Foundation',f'<div class="grid"><div class="card">إجمالي Debit<div class="kpi">{debit:.2f}</div></div><div class="card">إجمالي Credit<div class="kpi">{credit:.2f}</div></div></div><table><tr><th>الوقت</th><th>فرع</th><th>الحساب</th><th>Debit</th><th>Credit</th><th>Ref</th></tr>{tr}</table>')

@app.get('/audit',response_class=HTMLResponse)
def audit(s:Session=Depends(db)):
    rows=s.scalars(select(Audit).order_by(Audit.id.desc()).limit(100)).all(); tr=''.join(f'<tr><td>{x.created_at:%Y-%m-%d %H:%M}</td><td>{x.action}</td><td>{x.details}</td></tr>' for x in rows); return page('Audit Log',f'<table><tr><th>الوقت</th><th>العملية</th><th>التفاصيل</th></tr>{tr}</table>')
@app.get('/api/sync/pending')
def sync_pending(limit:int=100,s:Session=Depends(db)):
    rows=s.scalars(select(StockMove).where(StockMove.sync_state=='pending').order_by(StockMove.id).limit(min(limit,500))).all(); return {'node':os.getenv('NODE_ID','branch-local'),'events':[{'event_id':m.event_id,'created_at':m.created_at.isoformat(),'branch_id':m.branch_id,'product_id':m.product_id,'batch_id':m.batch_id,'qty_delta':m.qty_delta,'reason':m.reason,'ref':m.ref,'prev_hash':m.prev_hash,'event_hash':m.event_hash} for m in rows]}
@app.post('/api/sync/ack/{event_id}')
def sync_ack(event_id:str,s:Session=Depends(db)):
    m=s.scalar(select(StockMove).where(StockMove.event_id==event_id))
    if not m: raise HTTPException(404,'event not found')
    m.sync_state='synced'; s.commit(); return {'status':'ok','event_id':event_id}
@app.post('/api/backup')
def backup():
    if not DB_URL.startswith('sqlite'): raise HTTPException(400,'SQLite backup endpoint only')
    src=Path(DB_URL.replace('sqlite:///','',1)); src=src if src.is_absolute() else Path.cwd()/src; out=Path('/app/backups') if Path('/app/backups').exists() else Path('./backups'); out.mkdir(parents=True,exist_ok=True); dst=out/f'pharmacy-{dt.datetime.now():%Y%m%d-%H%M%S}.db'; shutil.copy2(src,dst); return {'status':'ok','file':str(dst)}

# v0.4 authentication and clinical/customer extensions
def current_user(request:Request,s:Session):
    token=request.cookies.get('pharmacy_session','')
    return s.scalar(select(User).where(User.session_token==token,User.active==1)) if token else None

def allowed(s:Session,u:User,perm:str):
    r=s.get(Role,u.role_id) if u else None
    return bool(r and (r.permissions=='*' or perm in (r.permissions or '').split(',')))

PUBLIC_PATHS={'/login','/health'}
PERM_PREFIX={'/users':'users','/accounting':'accounting','/suppliers':'suppliers','/reports':'reports','/pos':'pos','/inventory':'inventory','/returns':'returns','/customers':'pos','/prescriptions':'pos','/alternatives':'inventory','/settings':'users'}
@app.middleware('http')
async def auth_middleware(request:Request,call_next):
    path=request.url.path
    if path in PUBLIC_PATHS or path.startswith('/docs') or path.startswith('/openapi'):
        return await call_next(request)
    with Session(engine) as s:
        u=current_user(request,s)
        if not u:
            return HTMLResponse('Unauthorized',status_code=401) if path.startswith('/api/') else RedirectResponse('/login',303)
        for prefix,perm in PERM_PREFIX.items():
            if path.startswith(prefix) and not allowed(s,u,perm): return HTMLResponse('Forbidden',status_code=403)
    return await call_next(request)

@app.get('/login',response_class=HTMLResponse)
def login_page():
    return HTMLResponse('<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">'+CSS+'<title>تسجيل الدخول</title></head><body><div class="wrap" style="max-width:480px"><div class="card"><h1>eg4hosting pharmacy POS</h1><form method="post"><input name="username" placeholder="اسم المستخدم" required><input name="password" type="password" placeholder="كلمة المرور" required><button>دخول</button></form></div></div></body></html>')
@app.post('/login')
def login(username:str=Form(...),password:str=Form(...),s:Session=Depends(db)):
    u=s.scalar(select(User).where(User.username==username,User.active==1))
    if not u or not password_ok(password,u.password_hash): raise HTTPException(401,'بيانات الدخول غير صحيحة')
    u.session_token=secrets.token_urlsafe(32); s.add(Audit(action='LOGIN',details=username)); s.commit()
    r=RedirectResponse('/',303); r.set_cookie('pharmacy_session',u.session_token,httponly=True,samesite='lax',max_age=28800); return r
@app.get('/logout')
def logout(request:Request,s:Session=Depends(db)):
    u=current_user(request,s)
    if u: u.session_token=''; s.add(Audit(action='LOGOUT',details=u.username)); s.commit()
    r=RedirectResponse('/login',303); r.delete_cookie('pharmacy_session'); return r

@app.get('/customers',response_class=HTMLResponse)
def customers(s:Session=Depends(db)):
    rows=s.scalars(select(Customer).order_by(Customer.id.desc())).all(); tr=''.join(f'<tr><td>{x.id}</td><td>{x.name}</td><td>{x.phone}</td></tr>' for x in rows)
    return page('العملاء والمرضى',f'<div class="card"><form method="post"><input name="name" placeholder="الاسم" required><input name="phone" placeholder="الهاتف"><button>إضافة</button></form></div><table><tr><th>#</th><th>الاسم</th><th>الهاتف</th></tr>{tr}</table>')
@app.post('/customers')
def customer_add(name:str=Form(...),phone:str=Form(''),s:Session=Depends(db)):
    s.add(Customer(name=name,phone=phone)); s.add(Audit(action='CUSTOMER_ADD',details=name)); s.commit(); return RedirectResponse('/customers',303)

@app.get('/alternatives',response_class=HTMLResponse)
def alternatives(s:Session=Depends(db)):
    ps=s.scalars(select(Product).order_by(Product.trade_name)).all(); opts=''.join(f'<option value="{p.id}">{p.trade_name} - {p.active_ingredient}</option>' for p in ps)
    rows=s.execute(select(DrugAlternative,Product).join(Product,Product.id==DrugAlternative.product_id).order_by(DrugAlternative.id.desc())).all(); tr=''
    for a,p in rows:
        alt=s.get(Product,a.alternative_product_id); tr+=f'<tr><td>{p.trade_name}</td><td>{alt.trade_name if alt else "-"}</td><td>{a.note}</td></tr>'
    return page('بدائل الأدوية',f'<div class="card"><form method="post"><select name="product_id">{opts}</select><select name="alternative_product_id">{opts}</select><input name="note" placeholder="ملاحظة"><button>ربط بديل</button></form></div><table><tr><th>الدواء</th><th>البديل</th><th>ملاحظة</th></tr>{tr}</table>')
@app.post('/alternatives')
def alternative_add(product_id:int=Form(...),alternative_product_id:int=Form(...),note:str=Form(''),s:Session=Depends(db)):
    if product_id==alternative_product_id: raise HTTPException(400,'اختر دواء مختلف')
    s.add(DrugAlternative(product_id=product_id,alternative_product_id=alternative_product_id,note=note)); s.add(Audit(action='ALTERNATIVE_ADD',details=f'{product_id}->{alternative_product_id}')); s.commit(); return RedirectResponse('/alternatives',303)

@app.get('/prescriptions',response_class=HTMLResponse)
def prescriptions(s:Session=Depends(db)):
    cs=s.scalars(select(Customer).order_by(Customer.name)).all(); ps=s.scalars(select(Product).order_by(Product.trade_name)).all(); co=''.join(f'<option value="{x.id}">{x.name}</option>' for x in cs); po=''.join(f'<option value="{x.id}">{x.trade_name}</option>' for x in ps)
    rows=s.execute(select(Prescription,Customer).join(Customer).order_by(Prescription.id.desc()).limit(100)).all(); tr=''.join(f'<tr><td>{x.id}</td><td>{c.name}</td><td>{x.doctor_name}</td><td>{x.created_at:%Y-%m-%d}</td><td>{x.notes}</td></tr>' for x,c in rows)
    return page('الروشتات',f'<div class="card"><form method="post"><select name="customer_id">{co}</select><input name="doctor_name" placeholder="الطبيب"><select name="product_id">{po}</select><input name="qty" type="number" min="1" value="1"><input name="dosage" placeholder="الجرعة"><input name="notes" placeholder="ملاحظات"><button>حفظ الروشتة</button></form></div><table><tr><th>#</th><th>المريض</th><th>الطبيب</th><th>التاريخ</th><th>ملاحظات</th></tr>{tr}</table>')
@app.post('/prescriptions')
def prescription_add(customer_id:int=Form(...),doctor_name:str=Form(''),product_id:int=Form(...),qty:int=Form(1),dosage:str=Form(''),notes:str=Form(''),s:Session=Depends(db)):
    x=Prescription(customer_id=customer_id,doctor_name=doctor_name,notes=notes); s.add(x); s.flush(); s.add(PrescriptionItem(prescription_id=x.id,product_id=product_id,qty=qty,dosage=dosage)); s.add(Audit(action='PRESCRIPTION_ADD',details=f'id={x.id}')); s.commit(); return RedirectResponse('/prescriptions',303)

@app.get('/settings',response_class=HTMLResponse)
def settings(s:Session=Depends(db)):
    defaults={'pharmacy_name':'صيدلية تجريبية','tax_pct':'0','currency':'EGP','receipt_footer':'شكراً لزيارتكم'}; vals={x.key:x.value for x in s.scalars(select(PharmacySetting)).all()}; vals={**defaults,**vals}
    return page('إعدادات الصيدلية',f'<div class="card"><form method="post"><input name="pharmacy_name" value="{vals["pharmacy_name"]}"><input name="tax_pct" value="{vals["tax_pct"]}" type="number" step="0.01"><input name="currency" value="{vals["currency"]}"><input name="receipt_footer" value="{vals["receipt_footer"]}"><button>حفظ</button></form></div>')
@app.post('/settings')
def settings_save(pharmacy_name:str=Form(...),tax_pct:str=Form('0'),currency:str=Form('EGP'),receipt_footer:str=Form(''),s:Session=Depends(db)):
    for k,v in {'pharmacy_name':pharmacy_name,'tax_pct':tax_pct,'currency':currency,'receipt_footer':receipt_footer}.items():
        x=s.scalar(select(PharmacySetting).where(PharmacySetting.key==k))
        if x: x.value=v
        else: s.add(PharmacySetting(key=k,value=v))
    s.add(Audit(action='SETTINGS_SAVE',details=pharmacy_name)); s.commit(); return RedirectResponse('/settings',303)

@app.get('/receipt/{sale_id}',response_class=HTMLResponse)
def receipt(sale_id:int,s:Session=Depends(db)):
    sale=s.get(Sale,sale_id)
    if not sale: raise HTTPException(404,'الفاتورة غير موجودة')
    items=s.execute(select(SaleItem,Product).join(Product,Product.id==SaleItem.product_id).where(SaleItem.sale_id==sale_id)).all(); st={x.key:x.value for x in s.scalars(select(PharmacySetting)).all()}; name=st.get('pharmacy_name','eg4hosting pharmacy POS'); footer=st.get('receipt_footer','شكراً لزيارتكم'); currency=st.get('currency','EGP'); tr=''.join(f'<tr><td>{p.trade_name}</td><td>{i.qty}</td><td>{i.unit_price:.2f}</td><td>{i.qty*i.unit_price:.2f}</td></tr>' for i,p in items)
    return HTMLResponse(f'<!doctype html><html dir="rtl"><head><meta charset="utf-8"><style>body{{font-family:Tahoma;width:72mm;margin:auto;font-size:12px}}h2,p{{text-align:center}}table{{width:100%;border-collapse:collapse}}td,th{{padding:4px;border-bottom:1px dashed #777}}@media print{{button{{display:none}}}}</style></head><body><h2>{name}</h2><p>فاتورة #{sale.id}<br>{sale.created_at:%Y-%m-%d %H:%M}</p><table><tr><th>الصنف</th><th>ك</th><th>سعر</th><th>إجمالي</th></tr>{tr}</table><h3>الإجمالي: {sale.total:.2f} {currency}</h3><p>{footer}</p><button onclick="print()">طباعة</button></body></html>')

@app.get('/api/products/search')
def api_product_search(q:str='',branch_id:int|None=None,s:Session=Depends(db)):
    from .pharmacy_core_v07 import DrugProfile, product_meta
    from sqlalchemy import or_, and_
    def avars(t):
        vals={t}
        if any(c in t for c in 'اأإآىة'):
            n=t.replace('أ','ا').replace('إ','ا').replace('آ','ا').replace('ى','ي').replace('ة','ه'); vals.add(n)
            vals.add(n.replace('ا','أ',1))
        return vals
    raw=q.strip(); tokens=[x for x in raw.split() if x]
    base=select(Product,DrugProfile).outerjoin(DrugProfile,DrugProfile.product_id==Product.id)
    if tokens:
        groups=[]
        for token in tokens:
            patterns=[]
            # % is an explicit wildcard; without it partial matching is automatic.
            for v in avars(token):
                pat=v if '%' in v else f'%{v}%'
                patterns += [Product.trade_name.ilike(pat),Product.barcode.ilike(pat),Product.active_ingredient.ilike(pat),DrugProfile.arabic_name.ilike(pat),DrugProfile.generic_name.ilike(pat),DrugProfile.generic_name_ar.ilike(pat),Product.manufacturer.ilike(pat),DrugProfile.category.ilike(pat)]
            groups.append(or_(*patterns))
        base=base.where(and_(*groups))
    rows=s.execute(base.order_by(Product.trade_name).limit(40)).all(); out=[]
    for x,d in rows:
        m=product_meta(s,x)
        stock_q=select(func.coalesce(func.sum(Batch.qty),0)).where(Batch.product_id==x.id,Batch.qty>0,Batch.expiry>dt.date.today())
        if branch_id is not None: stock_q=stock_q.where(Batch.branch_id==branch_id)
        available=int(s.scalar(stock_q) or 0)
        out.append({'id':x.id,'barcode':x.barcode,'name':x.trade_name,'arabic_name':m['arabic_name'],'active':x.active_ingredient,'generic':m['generic_name'],'generic_ar':m['generic_name_ar'],'price':x.sale_price,'manufacturer':x.manufacturer,'category':m['category'],'level':m['level'],'level_label':m['level_label'],'level_icon':m['level_icon'],'rx_required':m['rx_required'],'instructions':m['instructions'],'available':available,'sellable':available>0})
    return out

# Replace only the POS, receipt and sales-return routes; retain legacy modules.
app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', '') not in {'/pos', '/receipt/{sale_id}', '/returns/sale'}]
from . import pharmacy_core_v07
from . import pos_v05

app.router.routes[:] = [r for r in app.router.routes if not (getattr(r, 'path', '') in {'/', '/reports'} and 'GET' in getattr(r, 'methods', set()))]
from . import catalog_reports
from . import pharmacy_core_v08

from . import eta_v09
from . import system_admin_v10

# Inventory Management v1.2 overrides the legacy read-only inventory page.
app.router.routes[:] = [r for r in app.router.routes if not (getattr(r, 'path', '') == '/inventory' and 'GET' in getattr(r, 'methods', set()))]
from . import inventory_v12
