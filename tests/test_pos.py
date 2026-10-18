import os, tempfile, uuid, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
os.environ['DB_URL']='sqlite:///'+str(Path(tempfile.mkdtemp())/'test.db')
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.main import app,engine,Batch,Sale,SaleItem,JournalEntry,PharmacySetting,Role,User,password_hash,SalesReturn
from app.pos_v05 import Offer,SaleTotals

client=TestClient(app)
assert client.post('/login',data={'username':'admin','password':'admin123'},follow_redirects=False).status_code==303

def cart(items=None):
    return dict(branch_id=1,customer_id=1,items=items or [{'product_id':1,'qty':2},{'product_id':2,'qty':1}],payments=[],request_key=str(uuid.uuid4()))
def pay(c):
    r=client.post('/api/pos/quote',json=c);assert r.status_code==200,r.text
    c['payments']=[{'method':'cash','amount':f'{r.json()["total"]/100:.2f}'}] if r.json()['total'] else []
    return r.json()
def state():
    with Session(engine) as s:return (s.scalar(select(func.count()).select_from(Sale)),s.scalar(select(func.sum(Batch.qty))))

def test_pages():
    assert client.get('/health').json()['version']=='1.1.3'
    for path in ['/','/pos','/offers','/customers','/prescriptions','/alternatives','/settings','/inventory','/returns','/accounting','/api/products/search?q=Panadol']:
        assert client.get(path).status_code==200,path
    assert TestClient(app).get('/api/pos/quote').status_code==401

def test_split_offer_tax_refund_and_idempotency():
    with Session(engine) as s:
        s.add(Offer(name='Quantity 10%',product_id=1,min_qty=2,percent='10'))
        s.add(PharmacySetting(key='tax_pct',value='10'));s.commit()
    c=cart();c['discount_amount']='5'
    q=pay(c)
    assert (q['subtotal'],q['discount'],q['tax'],q['total'])==(49500,4900,4460,49060)
    c['payments']=[{'method':'cash','amount':'200'},{'method':'card','amount':'290.60'}]
    before=state();r=client.post('/api/pos/checkout',json=c);assert r.status_code==200,r.text
    sale_id=r.json()['sale_id'];after=state();assert after==(before[0]+1,before[1]-3)
    assert client.post('/api/pos/checkout',json=c).json()['replayed'] is True
    assert state()==after
    changed={**c,'discount_amount':'4'};assert client.post('/api/pos/checkout',json=changed).status_code==409
    assert client.get(f'/receipt/{sale_id}').status_code==200
    with Session(engine) as s:
        entries=s.scalars(select(JournalEntry).where(JournalEntry.ref==f'SALE-{sale_id}')).all()
        assert round(sum(e.debit-e.credit for e in entries),2)==0
        ids=[(i.id,i.qty) for i in s.scalars(select(SaleItem).where(SaleItem.sale_id==sale_id))]
    for item_id,qty in ids:
        for _ in range(qty):
            assert client.post('/returns/sale',data={'sale_item_id':item_id,'qty':1},follow_redirects=False).status_code==303
        assert client.post('/returns/sale',data={'sale_item_id':item_id,'qty':1}).status_code==400
    with Session(engine) as s:
        assert round(s.scalar(select(func.sum(SalesReturn.amount)).where(SalesReturn.sale_id==sale_id)),2)==490.60
        assert round(s.scalar(select(func.sum(JournalEntry.debit)-func.sum(JournalEntry.credit))),2)==0
    assert state()[1]==before[1]

def test_invalid_and_atomic():
    before=state()
    for items in [[{'product_id':1,'qty':-1}],[{'product_id':1,'qty':0}],[{'product_id':1,'qty':1},{'product_id':1,'qty':1}],[{'product_id':1,'qty':1},{'product_id':2,'qty':100000}]]:
        assert client.post('/api/pos/checkout',json=cart(items)).status_code in (400,409,422)
    c=cart();pay(c);c['payments'][0]['amount']='1'
    assert client.post('/api/pos/checkout',json=c).status_code==400
    c=cart();c['items'][0]['discount_pct']='NaN'
    assert client.post('/api/pos/checkout',json=c).status_code==422
    assert state()==before

def test_permissions_and_branch():
    with Session(engine) as s:
        r=s.scalar(select(Role).where(Role.name=='Accountant'));s.add(User(username='acc',password_hash=password_hash('test'),role_id=r.id,branch_id=1))
        r=s.scalar(select(Role).where(Role.name=='Pharmacist'));s.add(User(username='pharm',password_hash=password_hash('test'),role_id=r.id,branch_id=2));s.commit()
    acc=TestClient(app);acc.post('/login',data={'username':'acc','password':'test'})
    assert acc.post('/api/pos/checkout',json=cart()).status_code==403
    ph=TestClient(app);ph.post('/login',data={'username':'pharm','password':'test'})
    assert ph.post('/api/pos/quote',json=cart()).status_code==403
    assert ph.post('/offers',data={'name':'bad','product_id':1,'min_qty':1,'percent':100}).status_code==403

def test_fefo_and_concurrency():
    with Session(engine) as s:
        for b in s.scalars(select(Batch).where(Batch.product_id==3)):b.qty=0
        expired=Batch(product_id=3,branch_id=1,batch_no='expired',expiry=dt.date.today()-dt.timedelta(days=1),qty=100,cost=5)
        first=Batch(product_id=3,branch_id=1,batch_no='first',expiry=dt.date.today()+dt.timedelta(days=1),qty=1,cost=5)
        later=Batch(product_id=3,branch_id=1,batch_no='later',expiry=dt.date.today()+dt.timedelta(days=10),qty=1,cost=5)
        s.add_all([expired,first,later]);s.commit();first_id=first.id;later_id=later.id
    c=cart([{'product_id':3,'qty':1}]);pay(c)
    r=client.post('/api/pos/checkout',json=c);assert r.status_code==200
    with Session(engine) as s:assert s.get(Batch,first_id).qty==0 and s.get(Batch,later_id).qty==1
    a=cart([{'product_id':3,'qty':1}]);pay(a);b=cart([{'product_id':3,'qty':1}]);pay(b)
    with ThreadPoolExecutor(2) as pool:codes=list(pool.map(lambda c:client.post('/api/pos/checkout',json=c).status_code,[a,b]))
    assert sorted(codes)==[200,409]
    with Session(engine) as s:assert s.get(Batch,later_id).qty==0

def test_mid_transaction_failure_rolls_back(monkeypatch):
    from app import pos_v05
    c=cart();pay(c);before=state()
    def fail(*args,**kwargs):raise RuntimeError('simulated ledger failure')
    monkeypatch.setattr(pos_v05,'add_move',fail)
    failing=TestClient(app,raise_server_exceptions=False)
    failing.cookies.update(client.cookies)
    assert failing.post('/api/pos/checkout',json=c).status_code==500
    assert state()==before
    with Session(engine) as s:assert s.scalar(select(SaleTotals).where(SaleTotals.request_key==c['request_key'])) is None


def test_windows_template_encoding_and_bundle_fallback(monkeypatch):
    from app.pos_v05 import load_pos_template
    from app.pos_template import POS_HTML
    from pathlib import Path
    original = Path.read_text
    def windows_read(self, *args, **kwargs):
        if self.name == 'pos.html':
            assert kwargs.get('encoding') == 'utf-8'
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', windows_read)
    assert load_pos_template() == POS_HTML
    assert client.get('/pos').status_code == 200
    def missing(self, *args, **kwargs):
        if self.name == 'pos.html':
            raise FileNotFoundError('simulated missing bundled asset')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', missing)
    assert load_pos_template() == POS_HTML
    assert client.get('/pos').status_code == 200
