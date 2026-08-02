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

## Tez boshlash — bitta fayl

Python 3.11+ o'rnatilgan bo'lsa, boshqa hech narsa sozlash kerak emas:

| Tizim | Nima qilasiz |
|---|---|
| **Windows** | `start.bat` ustiga ikki marta bosasiz |
| **macOS / Linux** | terminalda `./start.sh` |

Skript o'zi: `.venv` yasaydi, kutubxonalarni o'rnatadi, `.env` yaratib yangi
`SECRET_KEY` yozadi, bazani tayyorlaydi, demo ma'lumot qo'shadi va web
serverni ishga tushiradi. Oxirida ochish kerak bo'lgan havolalarni chiqaradi.

```
──────────────────────────────────────────────────────────────
  TAYYOR — quyidagi havolalarni brauzerda ochasiz
──────────────────────────────────────────────────────────────

  Admin panel:   http://localhost:8000/admin
  Login/parol:   admin / admin

  Ofis ekrani:   http://localhost:8000/kiosk/r2LTkyiEmcid...
  ... tarmoqdan: http://192.168.1.50:8000/kiosk/r2LTkyiEmcid...
  (bu havola maxfiy — xodimlarga tarqatmang)
```

Bayroqlar:

```bash
python start.py --no-demo      # demo ma'lumotsiz, bo'sh baza (haqiqiy ish)
python start.py --port 9000    # boshqa port
python start.py --setup-only   # faqat sozlash, serversiz
```

Ikkinchi va keyingi ishga tushirishlar tez bo'ladi — hamma narsa joyida
bo'lsa skript ularni qaytadan qilmaydi.

Bot hali ulanmagan bo'lsa panel ishlaydi, lekin QR ichidagi havola ishlamaydi.
Tokenni [@BotFather](https://t.me/BotFather) dan olib `.env` ga yozasiz — botni
ishga tushirish shart emas, `start.py` uni web server bilan birga o'zi
ko'taradi.

### QR skanerlanmayapti (telefon hech narsa qilmaydi)

Sabab deyarli har doim bitta: QR ichidagi havola noto'g'ri. Uni ko'rish uchun:

```bash
python manage.py qr-check          # Windows: tekshir.bat ga ikki marta bosing
```

Bu buyruq QR ichiga tushadigan aniq havolani chiqaradi va `BOT_TOKEN` bo'lsa
uni Telegramdagi haqiqiy username bilan solishtiradi.

Eng ko'p uchraydigan ikki xato:

* `BOT_USERNAME` ga botning **ko'rinadigan nomi** yozilgan (`Davomat tizimi`).
  U yerga `@` dan keyingi username yoziladi — probelsiz: `DavomatTizimiBot`.
* `.env` to'g'rilangan, lekin server qaytadan ishga tushirilmagan. `.env`
  faqat ishga tushganda o'qiladi, shuning uchun oynani yopib, `start.bat` ni
  yana bosish kerak.

<details>
<summary>Qo'lda sozlash (skript ishlamasa)</summary>

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env
.venv/bin/python manage.py secret        # SECRET_KEY yasab, .env ga yozing

.venv/bin/python manage.py init          # baza + jadval + ofis + kiosk
.venv/bin/python manage.py add-employee --name "Aliyev Aziz" --salary 10000000

# 1-terminal: web
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
# 2-terminal: bot
.venv/bin/python -m app.bot
```
</details>

Ochiladi:
* **Admin panel** — `http://localhost:8000/admin` (login `.env` dan)
* **Ofis ekrani** — `manage.py init` ko'rsatgan `/kiosk/<kalit>` havolasi

## Ekranlarni shu zahoti ko'rish — `preview/` papkasi

Hech narsa o'rnatmasdan, Python ham ishga tushirmasdan: `preview/index.html`
faylini brauzerda ochasiz (ustiga ikki marta bosish yetarli).

| Fayl | Nima ko'rsatadi |
|---|---|
| `preview/index.html` | Boshlash sahifasi, ikkalasiga havola |
| `preview/ofis-ekrani.html` | Xodimlar ko'radigan ekran: soat va QR, har 15 sekundda yangilanadi |
| `preview/admin-panel.html` | Kunlik jadval, oylik hisobi, oylik tabel |

Bular oddiy HTML fayllar — internet, server va hisob kerak emas. QR kodlar
haqiqiy, lekin tokenlari eskirgan, shuning uchun ular orqali **qayd qilib
bo'lmaydi**: bu ko'rgazma, ishlaydigan tizim emas.

## Demo: bot va serversiz ko'rib chiqish

Telegram bot tokeni hali bo'lmasa ham, tizimni to'liq ko'rish mumkin:

```bash
.venv/bin/python manage.py demo --period 2026-07
.venv/bin/uvicorn app.main:app --port 8000
```

6 ta namunaviy xodim va bir oylik davomat yaratiladi — vaqtida keladigan,
muntazam kechikadigan, erta ketadigan, tushlikda uzoq yuradigan va ba'zan
kelmaydigan. Bayram va ta'til kunlari ham bor. Undan keyin `/admin` va
`/admin/payroll` da hammasi jonli ko'rinadi, Excel eksporti ham ishlaydi.

Muhimi: yozuvlar **haqiqiy kod** orqali qo'shiladi (`record_event`), ya'ni
kechikish, tushlik oshig'i va oylik qo'lda "chizilmaydi" — demo ko'rsatgan
raqamlar real ishlashiga to'liq mos.

Bazada allaqachon xodim bo'lsa, demo ishlamaydi (`--force` bilan majburlash
mumkin). Haqiqiy ishga o'tishda bazani tozalab oling.

### Bayram taqvimi

```bash
.venv/bin/python manage.py holidays --year 2026
```

Qat'iy sanalar (Yangi yil, Navro'z, Mustaqillik kuni va boshqalar) o'zi
qo'shiladi. **Ramazon va Qurbon hayiti qo'lda kiritiladi** — ularning aniq
kunini O'zbekiston musulmonlari idorasi e'lon qiladi, shuning uchun tizim
faqat taxminiy sanani eslatadi. Bayram dam olish kuniga tushsa, ko'chirilgan
dam olish kunini ham qo'lda kiritasiz.

## VPS kerak emas

Tizim ofisdagi oddiy kompyuterda (eski noutbuk, mini-PC, Raspberry Pi) ishlaydi:

* **bot Telegram'ga o'zi ulanadi** (long polling) — tashqi IP, domen, port
  ochish, HTTPS sertifikat kerak emas, router/NAT ortidan ishlaydi;
* **QR sahifasini faqat ofisdagi ekran ochadi** — `localhost` yoki lokal tarmoq
  manzili yetarli.

```bash
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml run --rm web python manage.py init
```

Baza — bitta SQLite fayli (`./data/tabel.db`), Postgres ham kerak emas.
Yagona shart: kompyuter ish vaqtida yoniq turishi kerak.

Tafsilotlar, VPS varianti va nosozliklar — [`DEPLOY.md`](DEPLOY.md).

---

## Loyiha tuzilishi

| Fayl | Vazifasi |
|---|---|
| `start.py` | Bir buyruq bilan sozlash va ishga tushirish |
| `start.bat` / `start.sh` | Windows / macOS-Linux uchun ishga tushirgichlar |
| `tekshir.bat` / `tekshir.sh` | QR ichidagi havolani tekshirish (skanerlanmasa) |
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
