"""Inventory management v1.2: opening balances, adjustments, zeroing and auditable stock movements."""
import datetime as dt, shutil
from pathlib import Path
from html import escape
from fastapi import Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from .main import app, db, engine, Product, Branch, Batch, StockMove, Audit, add_move, page

REASONS={'OPENING':'رصيد افتتاحي','ADD':'إضافة رصيد','DAMAGE':'هالك / تالف','EXPIRED':'منتهي الصلاحية','INTERNAL':'استخدام داخلي','ADJUST':'تسوية','ZERO':'تصفير'}

def _backup_db():
    url=str(engine.url)
    if not url.startswith('sqlite:///'): return ''
    src=Path(url.replace('sqlite:///','',1))
    if not src.is_absolute(): src=(Path.cwd()/src).resolve()
    if not src.exists(): return ''
    d=src.parent/'backups'; d.mkdir(parents=True,exist_ok=True)
    dst=d/f'pharmacy-before-stock-{dt.datetime.now():%Y%m%d-%H%M%S}.db'; shutil.copy2(src,dst); return str(dst)

def _branches(s): return s.scalars(select(Branch).where(Branch.active==1).order_by(Branch.code)).all()

def _product(s,pid):
    p=s.get(Product,pid)
    if not p: raise HTTPException(404,'الصنف غير موجود')
    return p

@app.get('/inventory',response_class=HTMLResponse)
def inventory_v12(q:str='',branch_id:int|None=None,s:Session=Depends(db)):
    stmt=select(Batch,Product,Branch).join(Product,Product.id==Batch.product_id).join(Branch,Branch.id==Batch.branch_id)
    if branch_id: stmt=stmt.where(Batch.branch_id==branch_id)
    if q.strip():
        like=f'%{q.strip()}%'; stmt=stmt.where(or_(Product.trade_name.ilike(like),Product.barcode.ilike(like),Product.active_ingredient.ilike(like),Batch.batch_no.ilike(like)))
    rows=s.execute(stmt.order_by(Branch.code,Product.trade_name,Batch.expiry).limit(500)).all()
    total_qty=sum(b.qty for b,_,_ in rows); total_value=sum(b.qty*b.cost for b,_,_ in rows)
    bo='<option value="">كل الفروع</option>'+''.join(f'<option value="{b.id}" {"selected" if branch_id==b.id else ""}>{escape(b.code)} - {escape(b.name)}</option>' for b in _branches(s))
    tr=''.join(f'''<tr><td>{escape(br.code)}</td><td><b>{escape(p.trade_name)}</b><br><small>{escape(p.barcode)}</small></td><td>{escape(b.batch_no)}</td><td><b>{b.qty}</b></td><td>{b.cost:.2f}</td><td>{b.expiry}</td><td><a class="action" href="/inventory/adjust/{b.id}">تسوية</a><a class="action" href="/inventory/opening?product_id={p.id}&branch_id={br.id}">إضافة</a></td></tr>''' for b,p,br in rows)
    body=f'''<div class="grid"><div class="card"><div class="muted">الرصيد الظاهر</div><div class="kpi">{total_qty:,}</div></div><div class="card"><div class="muted">قيمة المخزون بالتكلفة</div><div class="kpi">{total_value:,.2f}</div></div></div>
    <div class="card"><h2>إدارة الأرصدة</h2><a class="action primary" href="/products">اختر دواء من الدليل لإضافة رصيد</a><a class="action" href="/counts">الجرد والتسويات</a><a class="action" href="/ledger">كشف حركة المخزون</a></div>
    <form method="get"><input name="q" value="{escape(q)}" placeholder="دواء / باركود / مادة فعالة / Batch" style="min-width:340px"><select name="branch_id">{bo}</select><button>بحث</button><a class="action" href="/inventory">مسح</a></form>
    <table><tr><th>الفرع</th><th>الصنف</th><th>Batch</th><th>الرصيد</th><th>التكلفة</th><th>الصلاحية</th><th>إجراء</th></tr>{tr}</table>'''
    return page('الأرصدة والمخزون',body)

@app.get('/inventory/opening',response_class=HTMLResponse)
def opening_form(product_id:int,branch_id:int|None=None,s:Session=Depends(db)):
    p=_product(s,product_id); bs=_branches(s); bo=''.join(f'<option value="{b.id}" {"selected" if branch_id==b.id else ""}>{escape(b.code)} - {escape(b.name)}</option>' for b in bs)
    body=f'''<div class="card"><h2>{escape(p.trade_name)}</h2><p class="muted">Barcode: {escape(p.barcode)} · سعر البيع الحالي: {p.sale_price:.2f} EGP</p>
    <form method="post"><input type="hidden" name="product_id" value="{p.id}"><label>الفرع<select name="branch_id" required>{bo}</select></label><label>نوع الحركة<select name="kind"><option value="OPENING">رصيد افتتاحي</option><option value="ADD">إضافة رصيد</option></select></label><label>Batch / Lot<input name="batch_no" value="OPENING" required></label><label>الصلاحية<input name="expiry" type="date" required></label><label>الكمية<input name="qty" type="number" min="1" required></label><label>تكلفة الوحدة<input name="cost" type="number" min="0" step="0.01" value="0" required></label><label>سعر البيع<input name="sale_price" type="number" min="0" step="0.01" value="{p.sale_price:.2f}" required></label><label>ملاحظة<input name="note" placeholder="سبب / مرجع"></label><button>حفظ الرصيد</button></form></div>'''
    return page('إضافة / رصيد افتتاحي',body)

@app.post('/inventory/opening')
def opening_save(product_id:int=Form(...),branch_id:int=Form(...),kind:str=Form('OPENING'),batch_no:str=Form(...),expiry:dt.date=Form(...),qty:int=Form(...),cost:float=Form(0),sale_price:float=Form(0),note:str=Form(''),s:Session=Depends(db)):
    p=_product(s,product_id)
    if not s.get(Branch,branch_id) or qty<=0 or cost<0 or sale_price<0 or kind not in {'OPENING','ADD'}: raise HTTPException(400,'بيانات الرصيد غير صحيحة')
    b=s.scalar(select(Batch).where(Batch.branch_id==branch_id,Batch.product_id==product_id,Batch.batch_no==batch_no.strip()))
    if b: b.qty+=qty; b.expiry=expiry; b.cost=cost
    else: b=Batch(branch_id=branch_id,product_id=product_id,batch_no=batch_no.strip(),expiry=expiry,qty=qty,cost=cost); s.add(b); s.flush()
    p.sale_price=sale_price; add_move(s,branch_id,product_id,b.id,qty,kind,'MANUAL',note.strip()); s.add(Audit(action=f'STOCK_{kind}',details=f'product={product_id} branch={branch_id} batch={b.id} qty=+{qty} note={note[:100]}')); s.commit()
    return RedirectResponse(f'/inventory?q={p.barcode}',303)

@app.get('/inventory/adjust/{batch_id}',response_class=HTMLResponse)
def adjust_form(batch_id:int,s:Session=Depends(db)):
    b=s.get(Batch,batch_id)
    if not b: raise HTTPException(404,'التشغيلة غير موجودة')
    p=s.get(Product,b.product_id); br=s.get(Branch,b.branch_id)
    body=f'''<div class="card"><h2>{escape(p.trade_name)}</h2><p>الفرع: <b>{escape(br.code)}</b> · Batch: <b>{escape(b.batch_no)}</b> · الرصيد الحالي: <b>{b.qty}</b></p>
    <form method="post"><label>الرصيد الفعلي الجديد<input name="physical_qty" type="number" min="0" value="{b.qty}" required></label><label>السبب<select name="reason"><option value="ADJUST">تسوية جرد</option><option value="DAMAGE">هالك / تالف</option><option value="EXPIRED">منتهي الصلاحية</option><option value="INTERNAL">استخدام داخلي</option></select></label><label>ملاحظة<input name="note" required placeholder="سبب التعديل"></label><button>اعتماد التسوية</button></form>
    <hr><h3>تصفير هذه التشغيلة</h3><p class="warn">سيتم أخذ Backup لقاعدة البيانات قبل التصفير، والحركة لن تُحذف من السجل.</p><form method="post" action="/inventory/zero/{b.id}"><input name="note" required placeholder="سبب التصفير"><input name="confirm" required placeholder="اكتب: تصفير"><button>تصفير الرصيد</button></form></div>'''
    return page('تسوية الرصيد',body)

@app.post('/inventory/adjust/{batch_id}')
def adjust_save(batch_id:int,physical_qty:int=Form(...),reason:str=Form('ADJUST'),note:str=Form(...),s:Session=Depends(db)):
    b=s.get(Batch,batch_id)
    if not b or physical_qty<0 or reason not in {'ADJUST','DAMAGE','EXPIRED','INTERNAL'}: raise HTTPException(400,'بيانات التسوية غير صحيحة')
    old=b.qty; delta=physical_qty-old; b.qty=physical_qty
    if delta: add_move(s,b.branch_id,b.product_id,b.id,delta,reason,'MANUAL-ADJUST',note.strip())
    s.add(Audit(action='STOCK_ADJUST',details=f'batch={b.id} old={old} new={physical_qty} reason={reason} note={note[:100]}')); s.commit(); return RedirectResponse('/inventory',303)

@app.post('/inventory/zero/{batch_id}')
def zero_batch(batch_id:int,note:str=Form(...),confirm:str=Form(...),s:Session=Depends(db)):
    if confirm.strip()!='تصفير': raise HTTPException(400,'اكتب كلمة تصفير للتأكيد')
    b=s.get(Batch,batch_id)
    if not b: raise HTTPException(404,'التشغيلة غير موجودة')
    backup=_backup_db(); old=b.qty
    if old: b.qty=0; add_move(s,b.branch_id,b.product_id,b.id,-old,'ZERO','MANUAL-ZERO',note.strip())
    s.add(Audit(action='STOCK_ZERO',details=f'batch={b.id} old={old} backup={backup} note={note[:100]}')); s.commit(); return RedirectResponse('/inventory',303)
