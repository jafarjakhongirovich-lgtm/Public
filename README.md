# Davomat va oylik tizimi (QR + Telegram)

Xodimlarning ishga kelib-ketishini ofisdagi ekranda turgan **QR kod** orqali qayd
qiladigan va shu ma'lumot asosida **oylikni hisoblab beradigan** platforma.

Kamera va Face ID kerak emas. Xodim ofisdagi ekrandagi QR ni telefon kamerasi
bilan skanerlaydi — Telegram o'zi ochiladi, vaqt bazaga tushadi.

---

## Qanday ishlaydi

```
   Ofisdagi ekran                Xodim telefoni              Server
  ┌──────────────┐              ┌──────────────┐         ┌──────────────┐
  │  QR (15 sek) │──skanerlash──▶│   Telegram   │────────▶│  bot + baza  │
  │  yangilanadi │              │ /start <tok> │         │  oylik hisob │
  └──────▲───────┘              └──────────────┘         └──────┬───────┘
         │                                                      │
         └───────────── imzolangan token ───────────────────────┘
```

1. Ofisdagi TV/monitor/planshet brauzerida `/kiosk/<maxfiy-kalit>` sahifasi
   to'liq ekranda turadi. QR har **15 sekundda** yangilanadi.
2. Xodim keladi, QR ni telefon kamerasi bilan skanerlaydi.
3. Telefon `https://t.me/<bot>?start=<token>` havolasini ochadi — Telegram
   o'zi ishga tushadi. Xodim hech narsa yozmaydi, hech qayerga kirmaydi.
4. Bot tokenni tekshiradi va xodimni Telegram akkaunti bo'yicha taniydi.
5. Bot nima deb tushunganini yozadi (`Ishga keldi — 09:03`) va **tuzatish
   tugmalarini** beradi: `Keldim / Tushlikka / Tushlikdan qaytdim / Ketdim`.
6. Oy oxirida admin panel oylikni hisoblab, Excel'ga chiqarib beradi.

### Nega bu ishonchli

| Aldash yo'li | Nima to'sqinlik qiladi |
|---|---|
| QR ni bir marta rasmga olib, keyin uydan ishlatish | Token **25 sekundda** o'ladi |
| QR rasmini hamkasbiga yuborish | Token yetib borguncha o'ladi; bitta token **faqat bir marta** ishlaydi |
| Bitta QR bilan ikki kishi kirishi | `used_tokens` jadvali — takror ishlatish rad etiladi |
| O'zi token yasab olish | Token server kaliti bilan **HMAC-SHA256** imzolangan |
| Telefon soatini o'zgartirish | Vaqt serverda hisoblanadi, telefonda emas |
| Boshqa ofisning QR'i bilan kirish | Xodim ofisga bog'lansa, boshqa ofis QR'i rad etiladi |

Halol bo'lgani uchun aytib qo'yish kerak: xodim uydan turib hamkasbiga
videoqo'ngiroq qilib QR ni **jonli** ko'rsatsa, bu tizim uni ushlamaydi. Buning
uchun tasodifiy tekshiruvlar yoki kelgusida kamera + Face ID kerak
(arxitektura shunga tayyor: `attendance_events.source` maydoni `QR`, `MANUAL`,
`FACE_ID` qiymatlarini oladi).

---

## Oylik qanday hisoblanadi

```
hisoblangan  = oylik × (to'lanadigan daqiqa ÷ oydagi norma daqiqa)
to'lanadigan = hisoblangan − ustama kamayishi
```

**To'lanmaydigan daqiqalar:** kechikish, erta ketish, tushlikdan oshgan vaqt
(har biriga *grace* muhlati alohida qo'llanadi), sababsiz kelmagan kun uchun
to'liq kunlik norma, to'lovsiz ruxsat kuni uchun to'liq kunlik norma.
Bayram va dam olish kunlari normaga umuman kirmaydi.

**Misol** (oylik 10 000 000 so'm, 23 ish kuni, kunlik norma 480 daqiqa,
grace 5 daqiqa):

| Holat | Natija |
|---|---|
| 09:04 da keldi | 4 daqiqa kechikish — muhlat ichida, ushlanma **yo'q** |
| 09:30 da keldi | 30 daqiqa kechikish, 25 daqiqasi hisobga olinadi → **≈22 645 so'm** |
| Kun kelmadi | 480 daqiqa → **≈434 783 so'm** |
| Tushlikda 90 daqiqa yurdi | 30 − 5 = 25 daqiqa hisobga olinadi |

### Huquqiy jihat

O'zbekiston Mehnat kodeksi bo'yicha ish haqidan to'g'ridan-to'g'ri "jarima"
ushlash cheklangan. Shuning uchun tizim ikki summani **alohida** yuritadi:

1. **Ishlanmagan vaqt** (`unpaid_time_deduction`) — ushlanma emas, shunchaki
   ishlanmagan daqiqalar uchun haq hisoblanmaydi. Qonuniy asosi mustahkam.
2. **Ustama/mukofot kamayishi** (`bonus_reduction`) — intizom uchun,
   rag'batlantirish qismidan. Hisoblangan summaning **20%idan oshmaydi**
   (`DeductionPolicy.max_deduction_percent`).

Standart sozlamada ikkinchisi **nolga teng** — ya'ni faqat ishlanmagan vaqt
hisoblanadi. Jarima summalarini qo'shmoqchi bo'lsangiz
`app/payroll.py` → `DeductionPolicy` ni sozlaysiz.

---

## Tez boshlash (lokal)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
.venv/bin/python manage.py secret        # SECRET_KEY yasab, .env ga yozing
# .env ga BOT_TOKEN va BOT_USERNAME ni ham yozing

.venv/bin/python manage.py init          # baza + jadval + ofis + kiosk
.venv/bin/python manage.py add-employee --name "Aliyev Aziz" --salary 10000000

# 1-terminal: web
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# 2-terminal: bot
.venv/bin/python -m app.bot
```

Ochiladi:
* **Admin panel** — `http://localhost:8000/admin` (login `.env` dan)
* **Ofis ekrani** — `manage.py init` ko'rsatgan `/kiosk/<kalit>` havolasi

Docker bilan ishga tushirish va VPS'ga o'rnatish — [`DEPLOY.md`](DEPLOY.md).

---

## Loyiha tuzilishi

| Fayl | Vazifasi |
|---|---|
| `app/security.py` | QR token: yasash, imzolash, muddat tekshirish |
| `app/attendance.py` | Skanerlashni qabul qilish, kunlik xulosani hisoblash |
| `app/payroll.py` | Oylik hisob-kitobi va ushlanma qoidalari |
| `app/bot.py` | Telegram bot (aiogram, long polling) |
| `app/main.py` | FastAPI: kiosk sahifasi + admin panel |
| `app/excel.py` | Oylik va tabel hisobotlarini `.xlsx` ga chiqarish |
| `app/models.py` | Baza modellari |
| `manage.py` | CLI: `init`, `add-employee`, `payroll`, `recompute`, … |

### Ikki qatlamli davomat

`attendance_events` — har bir skanerlashning **xom yozuvi**, hech qachon
o'chirilmaydi (faqat `is_voided` bilan bekor qilinadi).
`attendance` — shu yozuvlardan **qayta hisoblanadigan** kunlik xulosa.

Shu sababli har qanday tuzatishdan keyin `recompute_day()` chaqirilsa yetarli,
va qo'lda qilingan har bir o'zgarish `audit_log` ga tushadi — nizo chiqqanda
"kim, qachon, nimani o'zgartirdi" degan savolga javob bor.

---

## Testlar

```bash
.venv/bin/pip install pytest httpx2
.venv/bin/python -m pytest -q
```

95 test: token xavfsizligi (imzo buzish, muddat, takror ishlatish, boshqa
kalit), davomat hisobi (grace, tushlik oshig'i, erta ketish, bayram, ta'til),
oylik (to'liq oy, kelmagan kun, ushlanma chegarasi) va web qatlami (kiosk
endpoint bergan haqiqiy QR davomatga tushishi).

---

## Keyingi bosqichlar

* Tasodifiy tekshiruv: bot kun davomida random vaqtda screenshot so'raydi
* Kunlik/haftalik hisobotni Telegram guruhga avtomatik yuborish
* Kamera + Face ID (`EventSource.FACE_ID` allaqachon modelda bor)
* Telegram Mini App: xodim o'z tabeli va oyligini ko'radigan interfeys
