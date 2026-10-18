"""Windows launcher for the local eg4hosting pharmacy POS trial."""
import argparse
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
import subprocess
import queue


def splash_screen():
    import tkinter as tk
    from tkinter import ttk
    messages=queue.Queue()
    def listen():
        messages.put(sys.stdin.readline().strip() or 'ERROR')
    threading.Thread(target=listen,daemon=True).start()
    window=tk.Tk()
    window.title('eg4hosting pharmacy POS')
    window.overrideredirect(True)
    window.configure(bg='#112b3c')
    width,height=540,355
    x=(window.winfo_screenwidth()-width)//2;y=(window.winfo_screenheight()-height)//2
    window.geometry(f'{width}x{height}+{x}+{y}')
    window.attributes('-topmost',True)
    frame=tk.Frame(window,bg='#112b3c',highlightbackground='#258e88',highlightthickness=1)
    frame.pack(fill='both',expand=True)
    from app.pharmacy_brand import draw_splash_mark
    draw_splash_mark(frame).pack(pady=(12,0))
    tk.Label(frame,text='eg4hosting',font=('Segoe UI',26,'bold'),fg='white',bg='#112b3c').pack()
    tk.Label(frame,text='pharmacy POS',font=('Segoe UI',16),fg='#abc8d8',bg='#112b3c').pack(pady=(0,16))
    status=tk.Label(frame,text='Starting your pharmacy workspace...',font=('Segoe UI',10),fg='#bdd0da',bg='#112b3c');status.pack()
    style=ttk.Style(window);style.theme_use('clam')
    style.configure('Splash.Horizontal.TProgressbar',background='#43c9ae',troughcolor='#203e50',bordercolor='#203e50',lightcolor='#43c9ae',darkcolor='#43c9ae')
    progress=ttk.Progressbar(frame,style='Splash.Horizontal.TProgressbar',mode='indeterminate',length=370)
    progress.pack(pady=18);progress.start(15)
    tk.Label(frame,text='Version 1.1.2  |  Local workspace',font=('Segoe UI',9),fg='#7e9caf',bg='#112b3c').pack()
    started=time.monotonic()
    def poll():
        try:msg=messages.get_nowait()
        except queue.Empty:msg=''
        if msg=='READY':
            progress.stop();status.config(text='Ready. Opening your workspace...');window.after(350,window.destroy);return
        if msg=='ERROR' or time.monotonic()-started>120:
            progress.stop();status.config(text='Startup failed. Check the application console.',fg='#ffb6a8');window.after(4000,window.destroy);return
        window.after(100,poll)
    poll();window.mainloop()



def ensure_egyptian_catalog(root, bundle):
    """Import the bundled Egyptian catalog into the user's persistent DB once."""
    import csv, hashlib, sqlite3
    csv_path = bundle / 'data' / 'egyptian-drugs.csv'
    db_path = root / 'data' / 'pharmacy.db'
    if not csv_path.exists() or not db_path.exists():
        return 0
    con = sqlite3.connect(str(db_path))
    try:
        # app.main has already created/migrated these tables.
        existing = con.execute("select count(*) from products where barcode like 'EGD-%'").fetchone()[0]
        if existing >= 20000:
            return existing
        with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        def clean(v): return (v or '').strip()
        products=[]; meta=[]; seen=set()
        for r in rows:
            en=clean(r.get('commercial_name_en')); ar=clean(r.get('commercial_name_ar'))
            if not (en or ar): continue
            active=clean(r.get('scientific_name')); maker=clean(r.get('manufacturer'))
            key='|'.join([en,ar,active,maker]).encode('utf-8')
            barcode='EGD-'+hashlib.sha1(key).hexdigest()[:16].upper()
            if barcode in seen: continue
            seen.add(barcode)
            try: price=float(clean(r.get('price_egp')) or 0)
            except ValueError: price=0.0
            products.append((barcode,en or ar,active,'',clean(r.get('route')),maker,price,5))
            meta.append((barcode,ar,active,clean(r.get('drug_class'))))
        con.executemany('insert or ignore into products (barcode,trade_name,active_ingredient,strength,dosage_form,manufacturer,sale_price,reorder_level) values (?,?,?,?,?,?,?,?)', products)
        idmap=dict(con.execute("select barcode,id from products where barcode like 'EGD-%'").fetchall())
        profiles=[]
        for barcode,ar,active,category in meta:
            pid=idmap.get(barcode)
            if pid:
                profiles.append((pid,ar,active,'',category,'','','','','','Egyptian Drug Database (bundled catalog)',''))
        con.executemany('insert or ignore into drug_profiles (product_id,arabic_name,generic_name,generic_name_ar,category,indications,contraindications,warnings,side_effects,interactions,source,source_updated) values (?,?,?,?,?,?,?,?,?,?,?,?)', profiles)
        con.commit()
        return con.execute("select count(*) from products where barcode like 'EGD-%'").fetchone()[0]
    finally:
        con.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-splash', action='store_true')
    parser.add_argument('--splash-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--port', type=int, default=8088)
    args = parser.parse_args()
    if args.splash_child:
        bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        sys.path.insert(0, str(bundle))
        splash_screen()
        return 0
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'PharmacyERP'
    (root / 'data').mkdir(parents=True, exist_ok=True)
    (root / 'backups').mkdir(exist_ok=True)
    os.chdir(root)
    os.environ['DB_URL'] = 'sqlite:///' + (root / 'data' / 'pharmacy.db').as_posix()
    # Source runs and PyInstaller bundles both locate app from the bundle root.
    bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(bundle))
    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', args.port))
    except OSError:
        print(f'Port {args.port} is busy. Close the other instance, or run with --port 8089.')
        return 1
    splash=None
    if sys.platform=='win32' and not args.no_splash and not args.no_browser:
        command=([sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve())])+['--splash-child']
        try:
            splash=subprocess.Popen(command,stdin=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            pass  # Startup remains possible when a splash window cannot be created.
    def notify_splash(message):
        if splash and splash.poll() is None:
            try:
                splash.stdin.write((message+'\n').encode('ascii'));splash.stdin.flush();splash.stdin.close()
            except (OSError,ValueError):pass
    try:
        from app.main import app
        catalog_count = ensure_egyptian_catalog(root, bundle)
        print(f'Egyptian catalog ready: {catalog_count:,} items', flush=True)
        import uvicorn
    except BaseException:
        notify_splash('ERROR')
        raise
    url = f'http://127.0.0.1:{args.port}'
    print(f'eg4hosting pharmacy POS v1.1.2 — {url}', flush=True)
    print(f'Data and backups: {root}', flush=True)
    print('Trial login: admin / admin123 (unless changed).', flush=True)
    print('Keep this window open. Press Ctrl+C to stop.', flush=True)

    def open_when_ready():
        for _ in range(100):
            try:
                with urllib.request.urlopen(url + '/health', timeout=1) as response:
                    if response.status == 200:
                        notify_splash('READY')
                        webbrowser.open(url)
                        return
            except OSError:
                time.sleep(0.2)
        notify_splash('ERROR')

    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    from copy import deepcopy
    config = deepcopy(uvicorn.config.LOGGING_CONFIG)
    config['handlers']['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(root / 'pharmacy-error.log'),
        'maxBytes': 2_000_000, 'backupCount': 2,
        'encoding': 'utf-8', 'formatter': 'default',
    }
    config['loggers']['uvicorn']['handlers'].append('file')
    uvicorn.run(app, log_config=config, host='127.0.0.1', port=args.port, log_level='info')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
