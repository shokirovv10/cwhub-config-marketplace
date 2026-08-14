# CwHUB Config Marketplace PRO

Modern Flask multi-vendor marketplace for gaming configs.

## Highlights

- Dark, premium gaming UI with custom CSS/JS; no Bootstrap/Font Awesome dependency for critical layout.
- Marketplace search, filters, categories, seller profiles, cart and checkout.
- Seller workspace with dashboard, earnings, ledger, withdrawals, config upload/edit/hide.
- Admin control center with moderation, payments, receipts, orders, refunds, sellers, users, catalog, settings and audit log.
- Commission snapshot per order item.
- Wallet ledger with withdrawal reservation/release so duplicate payouts cannot consume the same available balance.
- Secure download authorization; config files are stored outside `static/`.
- CSRF protection, rate limits, RBAC, secure filenames and MIME checks.
- SQLite for development; PostgreSQL-ready through `DATABASE_URL`.
- Seed creates only the Super Admin and catalog config types/games; demo seller/user/config data is not created.

## Windows setup

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python seed.py
python check_project.py
python run.py
```

Open: `http://127.0.0.1:5000`

## Admin account

- Super Admin: values from `.env` (`ADMIN_USERNAME`, `ADMIN_PASSWORD`)

Change the admin password before any real deployment.

## Existing database

The redesign does not intentionally remove marketplace data. If your existing SQLite DB already exists, new columns/tables may require a migration; for a clean V5 install, start with a fresh `instance/cwhub.db`. The seed script also marks legacy demo configs as `DELETED`. For production schema changes, use Flask-Migrate/Alembic rather than `db.create_all()`.

## File storage

Development storage lives under `instance/uploads` and is never served as static public files. Downloads pass through authorization checks. The storage service is isolated so an S3/Cloudflare R2 provider can replace local storage later.

## Important financial flow

1. Buyer creates order.
2. Manual receipt is uploaded.
3. Admin approves payment.
4. Order becomes `COMPLETED`.
5. Seller earnings are credited through the wallet ledger.
6. Seller creates withdrawal request; amount is reserved immediately.
7. Admin marks payout paid or rejects it; rejection releases the reserved balance.

Never edit wallet balances directly from templates or client-side JavaScript.


## V6 qo‘shimchalari
- Dark Green Cyber dizayn: #121214 + #1A2421 + neon #00FF66.
- 1 MB bo‘lakli AJAX/chunk upload va progress bar.
- Seller verifikatsiyasi hujjat bilan.
- User Verified badge va admin tasdiqlashi.
- Super Admin seller workspace’dan ham foydalana oladi.
- Kafolat/qoidalar va Telegram yordam sahifalari.
- Demo seed ma’lumotlari ishlatilmaydi.
- Config turlari AIM, NO RECOIL, BHOP, MOVEMENT, CROSSHAIR, FPS BOOST, CONFIG PACK, OTHER.
- Username backend + database UNIQUE constraint bilan himoyalangan.

## V10 FINAL
Qo‘shimcha: Sevimlilar (Wishlist), Admin Foyda/Zarar va xarajatlar boshqaruvi, platforma e’lonlari, yaxshilangan seller ariza oqimi va mavjud V8 chunk upload tizimi.

## V10.1 yakuniy yangilanish

- Texnik xizmat va avtomatik tasdiqlash sozlamalari yangi switch-karta UI bilan ishlaydi.
- Barcha asosiy ko‘rinadigan yozuvlar o‘zbek tiliga moslashtirildi.
- Kafolat va foydalanish qoidalari professional tarzda kengaytirildi.
- Maxfiylik siyosati va Foydalanish shartlari sahifalari qo‘shildi.
- Footer ichiga huquqiy sahifalar havolalari qo‘shildi.


## Render + PostgreSQL

Loyiha `render.yaml` bilan Render Blueprint sifatida tayyorlangan. Git repository'ni Render'ga ulang va Blueprint'ni ishga tushiring. Web service `gunicorn` bilan boshlanadi, `/healthz` health-check sifatida ishlaydi va Render Postgres `DATABASE_URL` orqali ulanadi.

Muhim: Render web service filesystem'i odatda doimiy emas. CwHUB configlar, receiptlar, verification hujjatlari va avatarlarni productionda saqlash uchun S3-compatible storage (masalan Cloudflare R2) yoki Render persistent disk konfiguratsiyasini yoqing. PostgreSQL ma'lumotlarni saqlaydi, lekin yuklangan fayllarni emas.

### Render tezkor sozlama
1. GitHub/GitLab/Bitbucket'ga repository'ni push qiling.
2. Render'da New → Blueprint tanlang va `render.yaml`ni ulang.
3. `ADMIN_PASSWORD` secret qiymatini kiriting.
4. Deploy tugagach `/healthz` `ok: true` qaytarishini tekshiring.
5. Admin login qilib, Payment Cards, commission, seller verification va sayt sozlamalarini to'ldiring.


### Render PostgreSQL hotfix
Render start command automatically runs `python manage.py init-db` before Gunicorn so missing tables are created on first boot. Optional caught database errors now rollback the SQLAlchemy session immediately to prevent `InFailedSqlTransaction` cascading failures.

## Render uchun tezkor joylashtirish

1. GitHub repositoryga loyiha fayllarini yuklang. `.env` faylini yuklamang.
2. Render → New → Blueprint orqali `render.yaml`ni tanlang yoki Web Service sifatida ulang.
3. Render Environment’da `ADMIN_PASSWORD` uchun kuchli parol kiriting.
4. `DATABASE_URL` render.yaml orqali PostgreSQL’dan olinadi.
5. Build: `pip install -r requirements.txt`.
6. Start: `python manage.py init-db && gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app`.
7. Health check: `/healthz`.
8. Yordam: https://t.me/shokirjonshokirov

### Muhim production eslatma

Render servisining odatiy fayl tizimi doimiy emas. Config, chek, avatar va seller hujjatlarini uzoq muddat saqlash uchun Render Persistent Disk (faqat mos pullik xizmatlarda) yoki S3/R2 kabi obyekt saqlash tizimidan foydalaning. Hozirgi loyiha local storage bilan testga tayyor va storage abstraksiyasi keyinchalik S3/R2 ga almashtirishga moslangan.

## V20 — Biznes o‘sishi va xavfsizlik

V20 asosiy marketplace oqimini buzmasdan qo‘shimcha biznes va xavfsizlik modullarini qo‘shadi:

- Sotuvchi tariflari: Bepul, Pro, Ultra; tarifga qarab config limiti va komissiya.
- Tarif so‘rovi va administrator tomonidan faollashtirish.
- Kuponlar: foizli yoki qat’iy UZS chegirmasi, minimal buyurtma va foydalanish limiti.
- Buyurtmada kupon chegirmasi va komissiyani yakuniy summadan hisoblash.
- Config versiyalari: eski config fayli saqlanadi, versiya tarixi va qayta yuklab olish.
- Config xavfsizlik tekshiruvi: ZIP ichidagi executable/script kengaytmalar aniqlanadi.
- Duplicate chek aniqlash: SHA-256 fingerprint va fraud flag.
- Tez-tez buyurtma yaratish bo‘yicha anti-fraud signal.
- Support ticket tizimi.
- Config shikoyatlari va admin moderation.
- Fraud flaglarni admin ko‘rishi va yopishi.
- Taklif/referral havolalari va statistikasi.
- Sotuvchi darajasi: Yangi / O‘sayotgan / Pro / Top.
- Sinov rejimi flagi admin sozlamalariga qo‘shilgan.
- Login/register xavfsizlik eventlari.

### V20 local start

```bat
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install --prefer-binary -r requirements.txt
copy .env.example .env
python manage.py init-db
python seed.py
python check_project.py
python run.py
```

### V20 Render

`render.yaml` orqali PostgreSQL + Gunicorn deploy qilish mumkin. Render’da `DATABASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD` va production storage secretlarini Environment orqali boshqaring.

### Muhim production tavsiya

Config, receipt, verification hujjatlari va avatarlarni uzoq muddat saqlash uchun Render Persistent Disk yoki S3-compatible object storage (masalan Cloudflare R2) ishlating. Lokal filesystem test uchun mos, production uchun esa doimiy storage ishlatilishi kerak.


V25: maintenance mode keeps CSS/JS/image/health endpoints reachable so styling never disappears. Header search sizing is stabilized.
