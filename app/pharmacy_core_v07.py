"""Pharmacy Core v0.7: bilingual drug master, dispensing policies and customer discounts."""
from html import escape
from decimal import Decimal
from fastapi import Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import String, Integer, Text, ForeignKey, select, or_
from sqlalchemy.orm import Mapped, mapped_column, Session
from .main import app, Base, engine, db, Product, Customer, Audit, page, PERM_PREFIX

class DrugProfile(Base):
    __tablename__='drug_profiles'
    product_id:Mapped[int]=mapped_column(ForeignKey('products.id'),primary_key=True)
    arabic_name:Mapped[str]=mapped_column(String(180),default='')
    generic_name:Mapped[str]=mapped_column(String(180),default='')
    generic_name_ar:Mapped[str]=mapped_column(String(180),default='')
    category:Mapped[str]=mapped_column(String(100),default='Medicine')
    indications:Mapped[str]=mapped_column(Text,default='')
    contraindications:Mapped[str]=mapped_column(Text,default='')
    warnings:Mapped[str]=mapped_column(Text,default='')
    side_effects:Mapped[str]=mapped_column(Text,default='')
    interactions:Mapped[str]=mapped_column(Text,default='')
    source:Mapped[str]=mapped_column(String(240),default='')
    source_updated:Mapped[str]=mapped_column(String(40),default='')

class DispensingPolicy(Base):
    __tablename__='dispensing_policies'
    product_id:Mapped[int]=mapped_column(ForeignKey('products.id'),primary_key=True)
    level:Mapped[str]=mapped_column(String(24),default='otc') # otc/rx/restricted/controlled
    prescription_required:Mapped[int]=mapped_column(Integer,default=0)
    max_qty:Mapped[int]=mapped_column(Integer,default=0)
    instructions:Mapped[str]=mapped_column(Text,default='')

class CustomerDiscount(Base):
    __tablename__='customer_discounts'
    customer_id:Mapped[int]=mapped_column(ForeignKey('customers.id'),primary_key=True)
    percent:Mapped[str]=mapped_column(String(20),default='0')
    group_name:Mapped[str]=mapped_column(String(80),default='Regular')
    active:Mapped[int]=mapped_column(Integer,default=1)

Base.metadata.create_all(engine)
PERM_PREFIX.update({'/drug-guide':'inventory','/dispensing-policies':'users','/customer-discounts':'users'})

LEVELS={'otc':('عادي','🟢'),'rx':('روشتة','🟡'),'restricted':('مقيد','🟠'),'controlled':('جدول / خاضع للرقابة','🔴')}

def product_meta(s,p):
    d=s.get(DrugProfile,p.id); pol=s.get(DispensingPolicy,p.id)
    level=pol.level if pol else 'otc'; label,icon=LEVELS.get(level,LEVELS['otc'])
    return {'arabic_name':d.arabic_name if d else '', 'generic_name':d.generic_name if d else p.active_ingredient,
            'generic_name_ar':d.generic_name_ar if d else '', 'category':d.category if d else 'Medicine',
            'level':level,'level_label':label,'level_icon':icon,'rx_required':bool(pol and pol.prescription_required),
            'max_qty':pol.max_qty if pol else 0,'instructions':pol.instructions if pol else ''}

@app.get('/drug-guide',response_class=HTMLResponse)
def drug_guide(q:str='',s:Session=Depends(db)):
    stmt=select(Product,DrugProfile).outerjoin(DrugProfile,DrugProfile.product_id==Product.id)
    if q:
        like=f'%{q}%'; stmt=stmt.where(or_(Product.trade_name.ilike(like),Product.active_ingredient.ilike(like),Product.barcode.ilike(like),DrugProfile.arabic_name.ilike(like),DrugProfile.generic_name.ilike(like),DrugProfile.generic_name_ar.ilike(like)))
    rows=s.execute(stmt.order_by(Product.trade_name).limit(100)).all()
    tr=''.join(f'<tr><td><a href="/drug-guide/{p.id}">{escape(p.trade_name)}</a><br>{escape(d.arabic_name if d else "")}</td><td>{escape((d.generic_name if d else "") or p.active_ingredient)}</td><td>{escape(d.generic_name_ar if d else "")}</td><td>{escape(d.category if d else "Medicine")}</td><td>{product_meta(s,p)["level_icon"]} {product_meta(s,p)["level_label"]}</td></tr>' for p,d in rows)
    return page('دليل الأدوية المصري',f'<form method="get"><input name="q" value="{escape(q)}" placeholder="تجاري / عربي / English / المادة الفعالة / الاسم العلمي / Barcode" style="min-width:420px"><button>بحث</button></form><table><tr><th>الاسم التجاري</th><th>Generic / Active</th><th>الاسم العلمي عربي</th><th>التصنيف</th><th>الصرف</th></tr>{tr}</table>')

@app.get('/drug-guide/{product_id}',response_class=HTMLResponse)
def drug_card(product_id:int,s:Session=Depends(db)):
    p=s.get(Product,product_id)
    if not p: raise HTTPException(404,'الصنف غير موجود')
    d=s.get(DrugProfile,product_id) or DrugProfile(product_id=product_id)
    m=product_meta(s,p)
    def ta(name,label,val): return f'<label>{label}<textarea name="{name}" rows="3">{escape(val or "")}</textarea></label>'
    body=f'''<div class="card"><h2>{escape(p.trade_name)} — {escape(d.arabic_name or '')}</h2><p>{m['level_icon']} {m['level_label']} | Barcode: {escape(p.barcode)} | {escape(p.strength)}</p><form method="post">
    <input name="arabic_name" value="{escape(d.arabic_name or '')}" placeholder="الاسم العربي"><input name="generic_name" value="{escape(d.generic_name or p.active_ingredient)}" placeholder="Generic / Scientific name"><input name="generic_name_ar" value="{escape(d.generic_name_ar or '')}" placeholder="الاسم العلمي عربي"><input name="category" value="{escape(d.category or 'Medicine')}" placeholder="Category">
    {ta('indications','دواعي الاستعمال',d.indications)}{ta('contraindications','موانع الاستعمال',d.contraindications)}{ta('warnings','تحذيرات واحتياطات',d.warnings)}{ta('side_effects','الآثار الجانبية',d.side_effects)}{ta('interactions','التفاعلات الدوائية',d.interactions)}
    <input name="source" value="{escape(d.source or '')}" placeholder="المصدر"><input name="source_updated" value="{escape(d.source_updated or '')}" placeholder="تاريخ تحديث المصدر"><button>حفظ البطاقة الدوائية</button></form></div>'''
    return page('بطاقة الدواء',body)

@app.post('/drug-guide/{product_id}')
def drug_card_save(product_id:int,arabic_name:str=Form(''),generic_name:str=Form(''),generic_name_ar:str=Form(''),category:str=Form('Medicine'),indications:str=Form(''),contraindications:str=Form(''),warnings:str=Form(''),side_effects:str=Form(''),interactions:str=Form(''),source:str=Form(''),source_updated:str=Form(''),s:Session=Depends(db)):
    if not s.get(Product,product_id): raise HTTPException(404,'الصنف غير موجود')
    d=s.get(DrugProfile,product_id) or DrugProfile(product_id=product_id); s.add(d)
    for k,v in locals().copy().items():
        if k in {'arabic_name','generic_name','generic_name_ar','category','indications','contraindications','warnings','side_effects','interactions','source','source_updated'}: setattr(d,k,v.strip())
    s.add(Audit(action='DRUG_PROFILE_UPDATE',details=f'product={product_id}'));s.commit();return RedirectResponse(f'/drug-guide/{product_id}',303)

@app.get('/dispensing-policies',response_class=HTMLResponse)
def dispensing_policies(s:Session=Depends(db)):
    rows=s.scalars(select(Product).order_by(Product.trade_name)).all(); opts=''.join(f'<option value="{p.id}">{escape(p.trade_name)}</option>' for p in rows)
    tr=''.join(f'<tr><td>{escape(p.trade_name)}</td><td>{product_meta(s,p)["level_icon"]} {product_meta(s,p)["level_label"]}</td><td>{"نعم" if product_meta(s,p)["rx_required"] else "لا"}</td><td>{product_meta(s,p)["max_qty"] or "—"}</td><td>{escape(product_meta(s,p)["instructions"])}</td></tr>' for p in rows if s.get(DispensingPolicy,p.id))
    return page('سياسات صرف الأدوية',f'''<div class="card"><form method="post"><select name="product_id">{opts}</select><select name="level"><option value="otc">🟢 عادي</option><option value="rx">🟡 روشتة</option><option value="restricted">🟠 مقيد</option><option value="controlled">🔴 جدول / خاضع للرقابة</option></select><label><input type="checkbox" name="prescription_required" value="1"> يتطلب روشتة</label><input name="max_qty" type="number" min="0" value="0" placeholder="أقصى كمية (0=بدون)"><input name="instructions" placeholder="شروط وملاحظات الصرف"><button>حفظ السياسة</button></form></div><table><tr><th>الصنف</th><th>التصنيف</th><th>روشتة</th><th>أقصى كمية</th><th>الشروط</th></tr>{tr}</table>''')

@app.post('/dispensing-policies')
def dispensing_policy_save(product_id:int=Form(...),level:str=Form(...),prescription_required:int=Form(0),max_qty:int=Form(0),instructions:str=Form(''),s:Session=Depends(db)):
    if level not in LEVELS or max_qty<0 or not s.get(Product,product_id): raise HTTPException(400,'بيانات غير صحيحة')
    x=s.get(DispensingPolicy,product_id) or DispensingPolicy(product_id=product_id);s.add(x);x.level=level;x.prescription_required=1 if prescription_required else 0;x.max_qty=max_qty;x.instructions=instructions.strip();s.add(Audit(action='DISPENSING_POLICY_UPDATE',details=f'product={product_id} level={level}'));s.commit();return RedirectResponse('/dispensing-policies',303)

@app.get('/customer-discounts',response_class=HTMLResponse)
def customer_discounts(s:Session=Depends(db)):
    cs=s.scalars(select(Customer).order_by(Customer.name)).all();opts=''.join(f'<option value="{c.id}">{escape(c.name)}</option>' for c in cs)
    tr=''.join(f'<tr><td>{escape(c.name)}</td><td>{escape((s.get(CustomerDiscount,c.id).group_name if s.get(CustomerDiscount,c.id) else "Regular"))}</td><td>{escape((s.get(CustomerDiscount,c.id).percent if s.get(CustomerDiscount,c.id) else "0"))}%</td></tr>' for c in cs)
    return page('خصومات العملاء',f'<div class="card"><form method="post"><select name="customer_id">{opts}</select><input name="group_name" placeholder="الشريحة: VIP / شركة / موظفين" value="Regular"><input name="percent" type="number" min="0" max="100" step="0.01" value="0"><button>حفظ الخصم</button></form></div><table><tr><th>العميل</th><th>الشريحة</th><th>الخصم</th></tr>{tr}</table>')

@app.post('/customer-discounts')
def customer_discount_save(customer_id:int=Form(...),group_name:str=Form('Regular'),percent:Decimal=Form(...),s:Session=Depends(db)):
    if not s.get(Customer,customer_id) or not percent.is_finite() or not 0<=percent<=100: raise HTTPException(400,'بيانات الخصم غير صحيحة')
    x=s.get(CustomerDiscount,customer_id) or CustomerDiscount(customer_id=customer_id);s.add(x);x.group_name=group_name.strip()[:80] or 'Regular';x.percent=str(percent);x.active=1;s.add(Audit(action='CUSTOMER_DISCOUNT_UPDATE',details=f'customer={customer_id} percent={percent}'));s.commit();return RedirectResponse('/customer-discounts',303)
