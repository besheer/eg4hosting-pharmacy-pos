"""v0.9 ETA eReceipt integration scaffold: settings, immutable payload snapshots, offline queue and sandbox transport.
Production submission is deliberately disabled until official POS registration/credentials and current ETA schema are configured.
"""
import json, datetime as dt, hashlib, uuid
from html import escape
from fastapi import Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, select, func
from sqlalchemy.orm import Mapped, mapped_column, Session
from .main import app, Base, engine, db, Sale, SaleItem, Product, Branch, Audit, PharmacySetting, page, PERM_PREFIX
from .pos_v05 import SaleTotals, Payment

class ETAReceipt(Base):
    __tablename__='eta_receipts'
    id:Mapped[int]=mapped_column(primary_key=True)
    sale_id:Mapped[int]=mapped_column(ForeignKey('sales.id'),unique=True,index=True)
    created_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)
    updated_at:Mapped[dt.datetime]=mapped_column(DateTime,default=dt.datetime.utcnow)
    mode:Mapped[str]=mapped_column(String(20),default='sandbox')
    status:Mapped[str]=mapped_column(String(30),default='queued')
    local_uuid:Mapped[str]=mapped_column(String(64),unique=True)
    submission_id:Mapped[str]=mapped_column(String(120),default='')
    eta_uuid:Mapped[str]=mapped_column(String(120),default='')
    payload_json:Mapped[str]=mapped_column(Text)
    payload_hash:Mapped[str]=mapped_column(String(64))
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    last_error:Mapped[str]=mapped_column(Text,default='')
    last_attempt_at:Mapped[dt.datetime|None]=mapped_column(DateTime,nullable=True)

Base.metadata.create_all(engine)
PERM_PREFIX.update({'/eta':'users','/api/eta':'users'})

ETA_DEFAULTS={
 'eta_enabled':'0','eta_mode':'sandbox','eta_taxpayer_rin':'','eta_branch_code':'0','eta_pos_serial':'',
 'eta_activity_code':'','eta_client_id':'','eta_client_secret':'','eta_auto_queue':'1'
}

def settings(s):
    vals={x.key:x.value for x in s.scalars(select(PharmacySetting)).all()}
    return {**ETA_DEFAULTS,**vals}

def save_setting(s,k,v):
    x=s.scalar(select(PharmacySetting).where(PharmacySetting.key==k))
    if x:x.value=v
    else:s.add(PharmacySetting(key=k,value=v))

def make_payload(s,sale):
    st=settings(s); branch=s.get(Branch,sale.branch_id); totals=s.get(SaleTotals,sale.id)
    if not totals: raise HTTPException(400,'الفاتورة قديمة ولا تحتوي snapshot ضريبي v0.5+')
    snap=json.loads(totals.snapshot)
    items=[]
    for line in snap['lines']:
        p=s.get(Product,line['product_id'])
        items.append({'internalCode':str(p.id),'description':p.trade_name,'itemType':'EGS','itemCode':p.barcode,
            'unitType':'EA','quantity':line['qty'],'unitPrice':line['unit_price']/100,
            'netSale':line['net']/100,'total':line['total']/100,'commercialDiscount':line['discount']/100,
            'taxableItems':([{'taxType':'T1','amount':line['tax']/100,'subType':'V001','rate':float(snap['tax_pct'])}] if line['tax'] else [])})
    payments={p.method:p.amount/100 for p in s.scalars(select(Payment).where(Payment.sale_id==sale.id))}
    # Internal normalized envelope. Adapter maps this to the exact current ETA schema before live submission.
    return {'schema':'eg4-eta-normalized-v1','receiptNumber':str(sale.id),'dateTimeIssued':sale.created_at.replace(microsecond=0).isoformat()+'Z',
        'seller':{'rin':st['eta_taxpayer_rin'],'branchCode':st['eta_branch_code'],'activityCode':st['eta_activity_code'],'deviceSerialNumber':st['eta_pos_serial'],'branchName':branch.name if branch else ''},
        'buyer':{'type':'P','id':'','name':''},'items':items,'totalSales':snap['subtotal']/100,'totalCommercialDiscount':snap['discount']/100,
        'netAmount':(snap['subtotal']-snap['discount'])/100,'taxTotals':([{'taxType':'T1','amount':snap['tax']/100}] if snap['tax'] else []),
        'totalAmount':snap['total']/100,'paymentMethod':payments,'referenceOldUUID':''}

def queue_sale(s,sale_id):
    sale=s.get(Sale,sale_id)
    if not sale:raise HTTPException(404,'الفاتورة غير موجودة')
    prior=s.scalar(select(ETAReceipt).where(ETAReceipt.sale_id==sale_id))
    if prior:return prior
    payload=make_payload(s,sale); raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    h=hashlib.sha256(raw.encode()).hexdigest(); local=str(uuid.uuid5(uuid.NAMESPACE_URL,f'eg4hosting:eta:{sale_id}:{h}'))
    r=ETAReceipt(sale_id=sale_id,mode=settings(s)['eta_mode'],local_uuid=local,payload_json=raw,payload_hash=h)
    s.add(r);s.add(Audit(action='ETA_QUEUE',details=f'sale={sale_id} uuid={local}'));s.commit();return r

def sandbox_submit(s,r):
    r.attempts+=1;r.last_attempt_at=dt.datetime.utcnow();r.updated_at=dt.datetime.utcnow();r.last_error=''
    if not settings(s)['eta_taxpayer_rin'] or not settings(s)['eta_pos_serial']:
        r.status='needs_config';r.last_error='أدخل RIN و POS Serial من بيانات التسجيل لدى ETA';s.commit();return r
    r.status='sandbox_accepted';r.submission_id='SBX-'+r.local_uuid[:12].upper();r.eta_uuid=r.local_uuid
    s.add(Audit(action='ETA_SANDBOX_ACCEPT',details=f'sale={r.sale_id} submission={r.submission_id}'));s.commit();return r

@app.get('/eta',response_class=HTMLResponse)
def eta_dashboard(s:Session=Depends(db)):
    st=settings(s); rows=s.scalars(select(ETAReceipt).order_by(ETAReceipt.id.desc()).limit(100)).all()
    tr=''.join(f'<tr><td><a href="/receipt/{r.sale_id}">#{r.sale_id}</a></td><td>{escape(r.status)}</td><td>{escape(r.mode)}</td><td>{r.attempts}</td><td>{escape(r.submission_id or "-")}</td><td>{escape(r.last_error or "-")}</td><td><form method="post" action="/eta/{r.sale_id}/send"><button>إرسال/اختبار</button></form></td></tr>' for r in rows)
    counts=dict(s.execute(select(ETAReceipt.status,func.count()).group_by(ETAReceipt.status)).all())
    return page('ETA — الإيصال الإلكتروني',f'''<div class="card"><h2>حالة الربط</h2><p>الوضع الحالي: <b>{escape(st['eta_mode'])}</b> — Production غير مفعل في v0.9 حتى إدخال بيانات التسجيل واعتماد الـadapter على schema الحالية.</p><p>Queued: {counts.get('queued',0)} | Sandbox accepted: {counts.get('sandbox_accepted',0)} | Needs config: {counts.get('needs_config',0)}</p><a href="/eta/settings">إعدادات ETA</a></div><table><tr><th>فاتورة</th><th>الحالة</th><th>Mode</th><th>محاولات</th><th>Submission</th><th>آخر خطأ</th><th></th></tr>{tr or '<tr><td colspan="7">لا توجد إيصالات في الطابور.</td></tr>'}</table>''')

@app.get('/eta/settings',response_class=HTMLResponse)
def eta_settings(s:Session=Depends(db)):
    x=settings(s)
    return page('إعدادات ETA',f'''<div class="card"><form method="post"><label>Mode <select name="eta_mode"><option value="sandbox" {'selected' if x['eta_mode']=='sandbox' else ''}>Sandbox</option><option value="production" {'selected' if x['eta_mode']=='production' else ''}>Production (locked)</option></select></label><input name="eta_taxpayer_rin" value="{escape(x['eta_taxpayer_rin'])}" placeholder="Taxpayer RIN"><input name="eta_branch_code" value="{escape(x['eta_branch_code'])}" placeholder="Branch code"><input name="eta_pos_serial" value="{escape(x['eta_pos_serial'])}" placeholder="POS serial"><input name="eta_activity_code" value="{escape(x['eta_activity_code'])}" placeholder="Activity code"><input name="eta_client_id" value="{escape(x['eta_client_id'])}" placeholder="Client ID"><input name="eta_client_secret" type="password" value="" placeholder="Client Secret (اتركه فارغًا للاحتفاظ بالحالي)"><button>حفظ</button></form><p><b>أمان:</b> لا تضع بيانات Production إلا على جهاز الصيدلية. النسخة الحالية لا ترسل أسرارًا إلى أي خادم.</p></div>''')

@app.post('/eta/settings')
def eta_settings_save(eta_mode:str=Form('sandbox'),eta_taxpayer_rin:str=Form(''),eta_branch_code:str=Form('0'),eta_pos_serial:str=Form(''),eta_activity_code:str=Form(''),eta_client_id:str=Form(''),eta_client_secret:str=Form(''),s:Session=Depends(db)):
    if eta_mode not in ('sandbox','production'):raise HTTPException(400,'Mode غير صحيح')
    # Production stays locked until live adapter is explicitly enabled in a later verified build.
    if eta_mode=='production':raise HTTPException(400,'Production مقفول في v0.9 للحماية. استخدم Sandbox حتى اعتماد بيانات الربط الرسمية.')
    vals=locals().copy()
    for k in ('eta_mode','eta_taxpayer_rin','eta_branch_code','eta_pos_serial','eta_activity_code','eta_client_id'):
        save_setting(s,k,str(vals[k]).strip())
    if eta_client_secret.strip():save_setting(s,'eta_client_secret',eta_client_secret.strip())
    s.add(Audit(action='ETA_SETTINGS_SAVE',details=f'mode={eta_mode} rin={eta_taxpayer_rin}'));s.commit();return RedirectResponse('/eta/settings',303)

@app.post('/eta/{sale_id}/queue')
def eta_queue(sale_id:int,s:Session=Depends(db)):
    queue_sale(s,sale_id);return RedirectResponse('/eta',303)

@app.post('/eta/{sale_id}/send')
def eta_send(sale_id:int,s:Session=Depends(db)):
    r=queue_sale(s,sale_id)
    if r.mode!='sandbox':raise HTTPException(400,'Production transport غير مفعل في هذه النسخة')
    sandbox_submit(s,r);return RedirectResponse('/eta',303)

@app.post('/eta/queue-unsent')
def eta_queue_unsent(s:Session=Depends(db)):
    existing=set(s.scalars(select(ETAReceipt.sale_id)).all())
    n=0
    for sid in s.scalars(select(Sale.id).order_by(Sale.id)):
        if sid not in existing:
            try:queue_sale(s,sid);n+=1
            except HTTPException:pass
    s.add(Audit(action='ETA_QUEUE_UNSENT',details=f'queued={n}'));s.commit();return RedirectResponse('/eta',303)
