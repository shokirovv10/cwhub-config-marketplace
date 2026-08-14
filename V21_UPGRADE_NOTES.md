# CwHUB V21 — yangilanish

## Asosiy tuzatishlar
- Xaridor o‘zi sotib olgan config sahifasining o‘zida `Configni yuklab olish` tugmasini ko‘radi.
- Yuklab olish statistikasi xato qilsa ham qonuniy fayl yuklab olish bloklanmaydi.
- Savatcha endi server-side `CartItem` modeli bilan saqlanadi; session muammolariga bog‘liq emas.
- Eski session savatchalari bir marta avtomatik DB savatchasiga ko‘chiriladi.
- Admin panelda platforma to‘lov kartalari boshqaruvi saqlangan va admin ro‘yxatida karta raqami maskalanadi.
- Sotuvchi paneliga to‘lov rekvizitlari qo‘shildi: karta/hisob, asosiy rekvizit, o‘chirish va pul yechishda tanlash.
- Seller tasdiqlanganda wallet avtomatik yaratiladi.
- Cover rasm uchun chunk-upload token backend tomonidan ham qabul qilinadi.
- Upload tugagach tanlangan fayl nomi `Yuklandi:` holatiga o‘tadi.
- Jinja/Python smoke testlar yangilandi.

## Render
Deploydan oldin `python manage.py init-db` ishga tushishi kerak. `render.yaml` buni avtomatik bajaradi.
