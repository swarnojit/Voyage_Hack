#!/usr/bin/env python3
"""Cross-platform, zero-extra-dependency local launcher (Windows/macOS/Linux)."""
from pathlib import Path
import os
import sys

root = Path(__file__).resolve().parents[1]
file = root / '.env'
if not file.exists():
    sys.exit('Missing .env. First run: python scripts/bootstrap.py')
for line in file.read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key,value=line.split('=',1)
    os.environ.setdefault(key.strip(),value.strip())
os.chdir(root/'backend')
sys.path.insert(0,str(root/'backend'))
try:
    import uvicorn
except ImportError:
    sys.exit('Install first: python -m pip install -r backend/requirements.txt')
print('Open: http://127.0.0.1:8000/lab')
uvicorn.run('app.main:app',host='127.0.0.1',port=8000,workers=1,log_level='info')
