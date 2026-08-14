# CwHUB xavfsizlik qoidalari

CwHUB xavfsizlik qatlamlari sifatida CSRF himoyasi, parol xeshlash, rol asosidagi ruxsat, rate limiting, private fayl yuklash, random fayl nomlari, xavfsiz sessiyalar, DB rollback va secure download tekshiruvlarini qo‘llaydi.

Production uchun:
- `.env` GitHub’ga yuklanmaydi.
- Render Environment Variables orqali maxfiy qiymatlar beriladi.
- PostgreSQL ishlatiladi.
- Config, chek, avatar va verifikatsiya hujjatlari uchun persistent storage (Render persistent disk yoki S3/R2) ishlatiladi.
- Kuchli admin paroli ishlatiladi va zarur bo‘lsa `python manage.py reset-admin-password` orqali almashtiriladi.

Hech qanday dasturiy loyiha matematik ma’noda “100% zaifliksiz” deb kafolatlanmaydi; release oldidan dependency va server xavfsizligi muntazam yangilanadi.
