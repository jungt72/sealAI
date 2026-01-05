#!/usr/bin/env python3
import hashlib, json, os, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports"; OUT.mkdir(parents=True, exist_ok=True)
SKIP = {".git",".trash",".pytest_cache",".next","dist","build","__pycache__","coverage","node_modules",".venv",".mypy_cache"}
EXT = {".py":"python",".ts":"ts",".tsx":"tsx",".js":"js",".jsx":"jsx",".sql":"sql",".sh":"bash",".yml":"yaml",".yaml":"yaml",".toml":"toml",".json":"json"}
def files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.parts) & SKIP): yield p
def sha(p): 
    h=hashlib.sha256(); 
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(1<<20), b""): h.update(c)
    return h.hexdigest()
def loc(p):
    try: return sum(1 for _ in open(p,"rb"))
    except: return 0
rows=[]
for f in files():
    st=f.stat()
    rows.append({"path":str(f.relative_to(ROOT)),"size":st.st_size,"mtime":int(st.st_mtime),
                 "lang":EXT.get(f.suffix.lower(),"other"),"loc":loc(f),"sha256":sha(f)})
by_hash={}; [by_hash.setdefault(r["sha256"],[]).append(r["path"]) for r in rows]
dups={h:ps for h,ps in by_hash.items() if len(ps)>1}
with open(OUT/"inventory.json","w") as w: json.dump({"files":rows,"dups":dups}, w, indent=2)
print("Wrote reports/inventory.json")
