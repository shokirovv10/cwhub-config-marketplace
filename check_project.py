"""Static project check for CwHUB.
Run after installing requirements: python check_project.py
"""
import ast
import re
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent
errors = []

for py_file in ROOT.rglob('*.py'):
    if any(part == '__pycache__' for part in py_file.parts):
        continue
    try:
        ast.parse(py_file.read_text(encoding='utf-8'))
    except SyntaxError as exc:
        errors.append(f'Python syntax: {py_file}: {exc}')

env = Environment(loader=FileSystemLoader(ROOT / 'templates'))
env.filters['uz_status'] = lambda v: str(v).replace('_',' ').title()
env.filters['uz_role'] = lambda v: str(v)
for html_file in (ROOT / 'templates').rglob('*.html'):
    try:
        env.get_template(html_file.relative_to(ROOT / 'templates').as_posix())
    except Exception as exc:
        errors.append(f'Jinja template: {html_file}: {exc}')

endpoints = {'assets_css','assets_js','assets_image'}
for route_file in (ROOT / 'app').rglob('routes.py'):
    module = route_file.parent.name
    tree = ast.parse(route_file.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in {'route','get','post','put','patch','delete'} for d in node.decorator_list):
                endpoints.add(f'{module}.{node.name}')
refs = set()
for html_file in (ROOT / 'templates').rglob('*.html'):
    refs.update(re.findall(r"url_for\('([^']+)'", html_file.read_text(encoding='utf-8')))
missing = sorted(ref for ref in refs if ref not in endpoints and ref != 'static')
errors.extend(f'Missing endpoint: {ref}' for ref in missing)


# Deployment/security sanity checks
req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
if 'email-validator' not in req:
    errors.append('requirements.txt: email-validator mavjud emas')
if 'gunicorn' not in req:
    errors.append('requirements.txt: gunicorn mavjud emas')
render = (ROOT / 'render.yaml').read_text(encoding='utf-8') if (ROOT / 'render.yaml').exists() else ''
for needle in ['wsgi:app', '/healthz', 'DATABASE_URL', 'SUPPORT_TELEGRAM']:
    if needle not in render:
        errors.append(f'render.yaml: {needle} mavjud emas')
env_example = (ROOT / '.env.example').read_text(encoding='utf-8')
if 'https://t.me/shokirjonshokirov' not in env_example:
    errors.append('.env.example: Telegram yordam manzili noto‘g‘ri')
if (ROOT / '.env').exists():
    errors.append('XAVFSIZLIK: .env repository ichida mavjud. Uni GitHubga yuklamang.')

if errors:
    print('CwHUB CHECK FAILED')
    for error in errors:
        print(' -', error)
    sys.exit(1)
print('CwHUB CHECK PASSED')
print('Python syntax: OK')
print('Jinja templates: OK')
print('Template endpoints: OK')
