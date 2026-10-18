"""v1.0 system administration: company identity, paths, full backups, receipt and barcode settings."""
import base64, datetime as dt, json, os, shutil, zipfile
from pathlib import Path
from html import escape
import io
from fastapi import Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .main import app, db, PharmacySetting, Audit, Product, Batch, page, DB_URL, PERM_PREFIX
PERM_PREFIX.update({'/system-settings':'users','/backup-center':'users','/receipt-designer':'users','/barcode-labels':'inventory'})

def getset(s): return {x.key:x.value for x in s.scalars(select(PharmacySetting)).all()}
def save(s,data):
    for k,v in data.items():
        row=s.scalar(select(PharmacySetting).where(PharmacySetting.key==k))
        if row: row.value=str(v or '')
        else: s.add(PharmacySetting(key=k,value=str(v or '')))
    s.commit()

def data_root():
    if DB_URL.startswith('sqlite:///'):
        p=Path(DB_URL.replace('sqlite:///','',1)); return (p if p.is_absolute() else Path.cwd()/p).parent
    return Path('./data')

@app.get('/system-settings',response_class=HTMLResponse)
def system_settings(s:Session=Depends(db)):
    v=getset(s); f=lambda k,d='':escape(v.get(k,d),quote=True)
    logo=v.get('logo_data','')
    preview=f'<img src="{logo}" style="max-height:90px;max-width:240px">' if logo else '<span class="muted">لا يوجد لوجو مخصص</span>'
    return page('بيانات الصيدلية والمسارات',f'''<div class="grid"><div class="card"><h2>بيانات الشركة / الصيدلية</h2><form method="post" action="/system-settings/company"><input name="pharmacy_name" value="{f('pharmacy_name','eg4hosting pharmacy POS')}" placeholder="اسم الصيدلية"><input name="pharmacy_name_en" value="{f('pharmacy_name_en')}" placeholder="English name"><input name="address" value="{f('address')}" placeholder="العنوان"><input name="phone" value="{f('phone')}" placeholder="الهاتف"><input name="whatsapp" value="{f('whatsapp')}" placeholder="WhatsApp"><input name="email" value="{f('email')}" placeholder="البريد"><input name="tax_id" value="{f('tax_id')}" placeholder="الرقم الضريبي"><input name="commercial_reg" value="{f('commercial_reg')}" placeholder="السجل التجاري"><button>حفظ البيانات</button></form></div><div class="card"><h2>اللوجو</h2>{preview}<form method="post" action="/system-settings/logo" enctype="multipart/form-data"><input type="file" name="logo" accept="image/png,image/jpeg,image/webp" required><button>رفع اللوجو</button></form><p class="muted">PNG/JPG/WebP حتى 1MB. يدخل تلقائياً في الإيصال.</p></div></div>
<div class="card"><h2>المسارات</h2><form method="post" action="/system-settings/paths"><label>Backup<input name="backup_path" value="{f('backup_path',str(data_root()/'backups'))}"></label><label>Exports<input name="export_path" value="{f('export_path',str(data_root()/'exports'))}"></label><label>Receipts<input name="receipt_path" value="{f('receipt_path',str(data_root()/'receipts'))}"></label><button>حفظ واختبار المسارات</button></form><p class="muted">يمكن استخدام قرص آخر أو Shared Folder/NAS إذا كان حساب تشغيل البرنامج لديه صلاحية كتابة.</p></div>''')

@app.post('/system-settings/company')
def company(pharmacy_name:str=Form(...),pharmacy_name_en:str=Form(''),address:str=Form(''),phone:str=Form(''),whatsapp:str=Form(''),email:str=Form(''),tax_id:str=Form(''),commercial_reg:str=Form(''),s:Session=Depends(db)):
    save(s,{'pharmacy_name':pharmacy_name,'pharmacy_name_en':pharmacy_name_en,'address':address,'phone':phone,'whatsapp':whatsapp,'email':email,'tax_id':tax_id,'commercial_reg':commercial_reg}); s.add(Audit(action='COMPANY_SETTINGS',details=pharmacy_name)); s.commit(); return RedirectResponse('/system-settings',303)

@app.post('/system-settings/logo')
async def logo_upload(logo:UploadFile=File(...),s:Session=Depends(db)):
    b=await logo.read(); c=(logo.content_type or '').lower()
    if len(b)>1024*1024 or c not in {'image/png','image/jpeg','image/webp'}: raise HTTPException(400,'اللوجو يجب أن يكون PNG/JPG/WebP وأقل من 1MB')
    save(s,{'logo_data':f'data:{c};base64,'+base64.b64encode(b).decode()}); return RedirectResponse('/system-settings',303)

@app.post('/system-settings/paths')
def paths(backup_path:str=Form(...),export_path:str=Form(...),receipt_path:str=Form(...),s:Session=Depends(db)):
    for p in (backup_path,export_path,receipt_path):
        x=Path(p).expanduser(); x.mkdir(parents=True,exist_ok=True); test=x/'.write-test'; test.write_text('ok'); test.unlink()
    save(s,{'backup_path':backup_path,'export_path':export_path,'receipt_path':receipt_path}); return RedirectResponse('/system-settings',303)

@app.get('/backup-center',response_class=HTMLResponse)
def backup_center(s:Session=Depends(db)):
    v=getset(s); root=Path(v.get('backup_path',str(data_root()/'backups'))).expanduser(); root.mkdir(parents=True,exist_ok=True)
    files=sorted(root.glob('pharmacy-full-*.zip'),reverse=True)[:30]
    rows=''.join(f'<tr><td>{escape(x.name)}</td><td>{x.stat().st_size/1024/1024:.1f} MB</td><td>{dt.datetime.fromtimestamp(x.stat().st_mtime):%Y-%m-%d %H:%M}</td></tr>' for x in files)
    return page('النسخ الاحتياطي',f'''<div class="card"><h2>Full Pharmacy Backup</h2><p>قاعدة البيانات + الإعدادات + اللوجو + ملف تعريف النسخة.</p><form method="post" action="/backup-center/create"><button>إنشاء نسخة احتياطية الآن</button></form><p>المسار: <code>{escape(str(root))}</code></p></div><table><tr><th>الملف</th><th>الحجم</th><th>التاريخ</th></tr>{rows}</table>''')

@app.post('/backup-center/create',response_class=HTMLResponse)
def create_backup(s:Session=Depends(db)):
    v=getset(s); root=Path(v.get('backup_path',str(data_root()/'backups'))).expanduser(); root.mkdir(parents=True,exist_ok=True)
    dst=root/f'pharmacy-full-{dt.datetime.now():%Y%m%d-%H%M%S}.zip'
    if not DB_URL.startswith('sqlite:///'): raise HTTPException(400,'Full backup الحالي يدعم SQLite؛ قواعد السيرفر تحتاج dump خاص بالمحرك')
    src=Path(DB_URL.replace('sqlite:///','',1)); src=src if src.is_absolute() else Path.cwd()/src
    with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(src,'database/pharmacy.db'); z.writestr('settings.json',json.dumps(v,ensure_ascii=False,indent=2)); z.writestr('manifest.json',json.dumps({'created_at':dt.datetime.now().isoformat(),'app':'eg4hosting pharmacy POS','version':'1.0.0'},ensure_ascii=False))
    s.add(Audit(action='FULL_BACKUP',details=str(dst))); s.commit()
    return page('تم النسخ الاحتياطي',f'<div class="card"><h2>تم بنجاح</h2><p>{escape(str(dst))}</p><a class="action primary" href="/backup-center">رجوع</a></div>')

@app.get('/receipt-designer',response_class=HTMLResponse)
def receipt_designer(s:Session=Depends(db)):
    v=getset(s); f=lambda k,d='':escape(v.get(k,d),quote=True); ck=lambda k: 'checked' if v.get(k,'1')=='1' else ''
    return page('تصميم الإيصال',f'''<div class="card"><form method="post"><label>المقاس<select name="receipt_width"><option value="80" {'selected' if v.get('receipt_width','80')=='80' else ''}>80mm</option><option value="58" {'selected' if v.get('receipt_width')=='58' else ''}>58mm</option></select></label><label><input type="checkbox" name="show_logo" value="1" {ck('show_logo')}> اللوجو</label><label><input type="checkbox" name="show_address" value="1" {ck('show_address')}> العنوان</label><label><input type="checkbox" name="show_phone" value="1" {ck('show_phone')}> الهاتف</label><label><input type="checkbox" name="show_tax" value="1" {ck('show_tax')}> الرقم الضريبي</label><label>رسالة أسفل الإيصال<input name="receipt_footer" value="{f('receipt_footer','شكراً لزيارتكم')}"></label><button>حفظ قالب الإيصال</button></form><a class="action" href="/pos">فتح نقطة البيع</a></div>''')

@app.post('/receipt-designer')
def receipt_save(receipt_width:str=Form('80'),show_logo:str=Form('0'),show_address:str=Form('0'),show_phone:str=Form('0'),show_tax:str=Form('0'),receipt_footer:str=Form(''),s:Session=Depends(db)):
    save(s,{'receipt_width':receipt_width,'show_logo':show_logo,'show_address':show_address,'show_phone':show_phone,'show_tax':show_tax,'receipt_footer':receipt_footer}); return RedirectResponse('/receipt-designer',303)

@app.get('/barcode-labels',response_class=HTMLResponse)
def labels(q:str='',s:Session=Depends(db)):
    stmt=select(Product).order_by(Product.trade_name).limit(80)
    if q: stmt=select(Product).where(Product.trade_name.ilike(f'%{q}%')).order_by(Product.trade_name).limit(80)
    ps=s.scalars(stmt).all(); rows=''.join(f'<tr><td>{escape(x.trade_name)}</td><td>{escape(x.barcode)}</td><td>{x.sale_price:.2f}</td><td><a class="action" target="_blank" href="/barcode-label/{x.id}">طباعة</a></td></tr>' for x in ps)
    return page('طباعة الباركود',f'<form><input name="q" value="{escape(q,quote=True)}" placeholder="اسم الصنف"><button>بحث</button></form><table><tr><th>الصنف</th><th>Barcode</th><th>السعر</th><th></th></tr>{rows}</table>')

@app.get('/barcode-label/{product_id}',response_class=HTMLResponse)
def label(product_id:int,s:Session=Depends(db)):
    p=s.get(Product,product_id)
    if not p: raise HTTPException(404,'الصنف غير موجود')
    try:
        import barcode as bc
        from barcode.writer import SVGWriter
        code=(p.barcode or str(p.id)).strip(); kind='ean13' if code.isdigit() and len(code) in (12,13) else 'code128'
        buf=io.BytesIO(); bc.get(kind,code,writer=SVGWriter()).write(buf,options={'write_text':False,'module_height':10.0,'quiet_zone':1.0}); svg=buf.getvalue().decode('utf-8')
    except Exception:
        svg=f'<div class="code">{escape(p.barcode)}</div>'
    return HTMLResponse(f'''<!doctype html><html dir="rtl"><meta charset="utf-8"><style>body{{font:12px Tahoma;width:45mm;text-align:center;margin:2mm}}svg{{max-width:42mm;height:14mm}}.code{{font:700 18px monospace;letter-spacing:2px;border:1px solid;padding:8px;direction:ltr}}@media print{{button{{display:none}}}}@page{{margin:1mm}}</style><b>{escape(p.trade_name)}</b><div>{p.sale_price:.2f} EGP</div>{svg}<small>{escape(p.barcode)}</small><br><button onclick="print()">طباعة</button></html>''')
