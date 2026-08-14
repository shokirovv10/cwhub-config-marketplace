# Render tekshiruvi

`/auth/register` uchun DB xatosi endi logga chiqariladi va transaction request oxirida rollback qilinadi.

Build: `pip install -r requirements.txt`
Start: `python manage.py init-db && gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app`
Health: `/healthz`
## V19: Fayl yuklash `storage is not defined`

Agar `/api/uploads/chunk/init` da `name 'storage' is not defined` chiqsa, API blueprint storage service importidan foydalanadi. V19 shu importni to‘g‘rilaydi. Config fayli, cover rasm, seller verification hujjati va payment receipt bir xil chunk upload API orqali ishlaydi.
