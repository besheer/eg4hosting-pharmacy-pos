"""Fast import of the bundled Egyptian Drug Database into the local master catalog."""
import csv, hashlib, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
CSV=ROOT/'data'/'egyptian-drugs.csv'
if not CSV.exists(): raise SystemExit(f'Missing bundled catalog: {CSV}')
from app.main import Session, engine, Product, Audit
from app.pharmacy_core_v07 import DrugProfile
from sqlalchemy import select

def txt(v): return (v or '').strip()
def code(r):
    key='|'.join([txt(r.get('commercial_name_en')),txt(r.get('commercial_name_ar')),txt(r.get('scientific_name')),txt(r.get('manufacturer'))]).encode('utf-8')
    return 'EGD-'+hashlib.sha1(key).hexdigest()[:16].upper()
with CSV.open('r',encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
rows=[r for r in rows if txt(r.get('commercial_name_en')) or txt(r.get('commercial_name_ar'))]
print(f'Loaded {len(rows)} catalog rows from {CSV.name}')
with Session(engine) as s:
    existing=set(s.scalars(select(Product.barcode).where(Product.barcode.like('EGD-%'))).all())
    new=[]; seen=set(existing)
    for r in rows:
        c=code(r)
        if c in seen: continue
        seen.add(c)
        try: price=float(txt(r.get('price_egp')) or 0)
        except ValueError: price=0.0
        new.append({'barcode':c,'trade_name':txt(r.get('commercial_name_en')) or txt(r.get('commercial_name_ar')),'active_ingredient':txt(r.get('scientific_name')),'strength':'','dosage_form':txt(r.get('route')),'manufacturer':txt(r.get('manufacturer')),'sale_price':price,'reorder_level':5})
    if new: s.bulk_insert_mappings(Product,new); s.commit()
    idmap=dict(s.execute(select(Product.barcode,Product.id).where(Product.barcode.like('EGD-%'))).all())
    prof_existing=set(s.scalars(select(DrugProfile.product_id).where(DrugProfile.product_id.in_(idmap.values()))).all()) if idmap else set()
    profiles=[]
    bycode={code(r):r for r in rows}
    for c,pid in idmap.items():
        if pid in prof_existing: continue
        r=bycode.get(c)
        if not r: continue
        profiles.append({'product_id':pid,'arabic_name':txt(r.get('commercial_name_ar')),'generic_name':txt(r.get('scientific_name')),'generic_name_ar':'','category':txt(r.get('drug_class')),'indications':'','dosage_adult':'','dosage_pediatric':'','contraindications':'','warnings':'','side_effects':'','interactions':'','pregnancy_lactation':'','renal_hepatic':'','storage':'','therapeutic_class':txt(r.get('drug_class')),'pharmacist_notes':'','source':'Egyptian Drug Database (bundled catalog)','source_updated':''})
    if profiles: s.bulk_insert_mappings(DrugProfile,profiles)
    s.add(Audit(action='EGYPTIAN_CATALOG_IMPORT',details=f'rows={len(rows)} created={len(new)} profiles={len(profiles)}'))
    s.commit()
print(f'RESULT: total={len(rows)} created={len(new)} profiles={len(profiles)}')
