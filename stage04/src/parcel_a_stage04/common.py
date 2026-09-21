"""Small, bounded I/O helpers; Stage 04 has no analytical network adapter."""
import csv
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime,timezone


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return h.hexdigest()


def now():return datetime.now(timezone.utc).isoformat()

def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def csv_write(path,rows,fields=()):
    columns=list(dict.fromkeys([*fields,*(k for r in rows for k in r)]));path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def csv_read(path):
    old=csv.field_size_limit();size=Path(path).stat().st_size
    if size>250_000_000:raise ValueError('Analytical table exceeds the Stage 04 input budget')
    try:
        csv.field_size_limit(max(old,size))
        with Path(path).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
    finally:csv.field_size_limit(old)


def relative(root,name):
    p=Path(name);root=Path(root).resolve()
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:raise ValueError('Unsafe package reference')
    full=root/p
    if root not in full.resolve().parents or full.is_symlink() or not full.is_file():raise ValueError('Missing or unsafe package file: '+name)
    return full


def number(value):
    if isinstance(value,bool):raise ValueError('Boolean is not an analytical value')
    x=float(value)
    if not math.isfinite(x):raise ValueError('Non-finite analytical value')
    return x


def close(a,b,rel=1e-8,abs_tol=1e-8):return math.isclose(number(a),number(b),rel_tol=rel,abs_tol=abs_tol)

def unique(rows,key):
    out={}
    for row in rows:
        k=key(row)
        if k in out:raise ValueError('Duplicate source key: '+str(k))
        out[k]=row
    return out
