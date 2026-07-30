# O'rnatish qo'llanmasi

Kod bilim shart emas — quyidagi buyruqlarni tartib bilan bajarsangiz yetarli.

---

## 1. Telegram bot yasash (5 daqiqa)

1. Telegramda [@BotFather](https://t.me/BotFather) ni oching.
2. `/newbot` yuboring. Bot nomini va username'ini kiritasiz
   (username `bot` bilan tugashi kerak, masalan `KompaniyaTabelBot`).
3. BotFather sizga **token** beradi — `8123456789:AAH...` ko'rinishida.
   Bu tokenni hech kimga bermang.
4. `/setdescription` bilan tavsif qo'shsangiz bo'ladi (ixtiyoriy).

> **Diqqat:** bu tizimda bot guruhga qo'shilishi **shart emas**. Xodimlar
> bot bilan shaxsiy yozishmada ishlaydi, shuning uchun `/setprivacy` bilan
> ham ishlashingiz kerak emas.

---

## 2. Qayerda ishga tushirish: VPS kerakmi?

**Kerak emas.** Ikkita variant bor, ikkinchisi ko'pchilikka mos keladi.

### Eng oson yo'l — `start.bat` / `start.sh`

Python 3.11+ o'rnatilgan bo'lsa, quyidagi bo'limlarni o'qimasdan ham
boshlash mumkin:

* **Windows** — `start.bat` ustiga ikki marta bosing
* **macOS / Linux** — `./start.sh`

Skript `.venv`, kutubxonalar, `.env`, `SECRET_KEY` va bazani o'zi tayyorlaydi,
demo ma'lumot qo'shadi va serverni ishga tushiradi. Docker ham kerak emas.
Bot tokenini keyinroq `.env` ga yozib qo'yasiz.

Docker bilan ishlashni xohlasangiz yoki VPS'ga o'rnatmoqchi bo'lsangiz —
pastdagi variantlarni o'qing.

### Variant A — oddiy kompyuterda (VPS'siz, pulsiz)

Tizim ofisdagi (yoki uydagi) oddiy kompyuterda ishlaydi. Sabab:

* **bot Telegram'ga o'zi ulanadi** (long polling) — tashqi IP, domen, port
  ochish, HTTPS sertifikat kerak emas, NAT/router ortidan ishlaydi;
* **QR sahifasini faqat ofisdagi ekran ochadi** — `localhost` yoki lokal
  tarmoq manzili yetarli, internetdan ochilishi shart emas.

Yaraydi: ish kompyuteri, eski noutbuk, mini-PC, Raspberry Pi.

```bash
cp .env.example .env          # to'ldirasiz (3-bo'limga qarang)
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml run --rm web python manage.py init
```

Baza `./data/tabel.db` faylida bo'ladi — Postgres ham kerak emas.
Docker o'rnatmoqchi bo'lmasangiz, Docker'siz ham bo'ladi (README'dagi
«Tez boshlash» bo'limi).

**Yagona shart:** kompyuter ish vaqtida yoniq turishi kerak. O'chgan bo'lsa
o'sha paytdagi kelish-ketish yozilmaydi (keyin qo'lda kiritiladi).
Nozik joyi shu — quvvat o'chsa yoki kompyuter uxlab qolsa, ma'lumot yo'qoladi.
Shuning uchun uyquni o'chirib qo'ying:

```bash
# Ubuntu
sudo systemctl mask sleep.target suspend.target hibernate.target
# Windows: Sozlamalar -> Quvvat -> Uyqu -> Hech qachon
```

Va zaxira nusxani ko'chirib qo'yishni odat qiling — bu shunchaki bitta fayl:

```bash
cp data/tabel.db "backup-$(date +%F).db"
```

### Variant B — VPS (agar kompyuter doim yoniq turolmasa)

Eng arzon VPS yetarli: **1 GB RAM, 1 CPU, Ubuntu 22.04/24.04**.
Domen va HTTPS bu holatda ham shart emas, lekin admin paneli internetdan
ochiladigan bo'lsa — HTTPS qo'shish kerak (5-bo'limga qarang).

```bash
# Docker o'rnatish
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# chiqib, qaytadan kiring (guruh o'zgarishi kuchga kirishi uchun)
```

Keyin 4-bo'limdagi `docker compose up -d` (Postgres bilan) ishlatiladi.

---

## 3. Loyihani ko'chirish va sozlash

```bash
git clone <repo-manzili> tabel
cd tabel
cp .env.example .env
```

`.env` faylini tahrirlang (`nano .env`):

```ini
# Maxfiy kalit — quyidagi buyruq bilan yasang va natijasini shu yerga yozing:
#   docker compose run --rm web python manage.py secret
SECRET_KEY=<yasagan-kalitingiz>

# Postgres paroli — o'zingiz o'ylab topasiz
POSTGRES_PASSWORD=<kuchli-parol>

# BotFather bergan token va bot username (@ belgisiz)
BOT_TOKEN=8123456789:AAH...
BOT_USERNAME=KompaniyaTabelBot

# Admin panel logini
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<kuchli-parol>

TIMEZONE=Asia/Tashkent
QR_REFRESH_SECONDS=15
QR_TTL_SECONDS=25
```

> `SECRET_KEY` ni keyinchalik o'zgartirsangiz, o'sha paytda ekranda turgan
> QR'lar bir zumda kuchini yo'qotadi (bu xavfsizlik uchun to'g'ri xatti-harakat).

---

## 4. Ishga tushirish

**Variant A** (oddiy kompyuter, SQLite):

```bash
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml run --rm web python manage.py init
```

**Variant B** (VPS, Postgres):

```bash
docker compose up -d --build
docker compose run --rm web python manage.py init
```

Oxirgi buyruq boshlang'ich ma'lumotni yaratadi va **kiosk havolasini** chiqaradi:

```
Ofis ekranida ochiladigan havolalar (maxfiy!):

  Kirish eshigi ekrani [Bosh ofis]
    Shu kompyuterda:      http://localhost:8000/kiosk/aBcD1234...
    Lokal tarmoqdan:      http://192.168.1.50:8000/kiosk/aBcD1234...
```

Havola ikki ko'rinishda chiqadi — ekran shu kompyuterda bo'lsa `localhost`,
lokal tarmoqdagi boshqa qurilmada (TV, planshet) bo'lsa IP manzilli.
Portni o'zgartirgan bo'lsangiz: `manage.py kiosks --port 9000`.

Tekshirish:

```bash
curl http://localhost:8000/healthz          # {"ok":true,...}
docker compose logs -f bot                  # "bot ishga tushdi: @..."
```

---

## 5. Tashqariga chiqarish (nginx) — faqat Variant B uchun

> Variant A (oddiy kompyuter) da bu bo'lim **kerak emas** — 6-bo'limga o'ting.
> Tizim lokal tarmoqda ishlaydi, internetga chiqarilmaydi.


`docker-compose.yml` web servisni faqat `127.0.0.1:8000` ga bog'laydi, ya'ni
tashqaridan ochilmaydi. Oldiga nginx qo'yamiz:

```bash
sudo apt install -y nginx
sudo tee /etc/nginx/sites-available/tabel > /dev/null <<'EOF'
server {
    listen 80;
    server_name tabel.kompaniya.uz;   # yoki server IP manzili

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # Kiosk IP cheklovi ishlashi uchun bu sarlavha majburiy:
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/tabel /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Domeningiz bo'lsa HTTPS qo'shing (admin paroli shifrlanmagan holda ketmasligi
uchun **juda tavsiya qilinadi**):

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tabel.kompaniya.uz
```

---

## 6. Ofis ekranini sozlash

1. TV / monitor / eski planshetga brauzer o'rnating (Chrome yoki Firefox).
2. `http://tabel.kompaniya.uz/kiosk/<kalit>` havolasini ochib, **to'liq ekran**
   rejimiga o'tkazing (`F11`).
3. Ekran o'chib qolmasligi uchun:
   ```bash
   # Ubuntu bilan ishlayotgan mini-PC bo'lsa:
   gsettings set org.gnome.desktop.session idle-delay 0
   gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
   ```
   Android planshetda: *Sozlamalar → Ekran → Kutish vaqti → Hech qachon*.
4. Chrome'ni kiosk rejimida avtomatik ochish (ixtiyoriy):
   ```bash
   chromium --kiosk --incognito "http://tabel.kompaniya.uz/kiosk/<kalit>"
   ```

Sahifa serverga aloqa yo'qolsa ekranda ogohlantirish chiqaradi va aloqa
qaytganda o'zi tiklanadi — qo'lda yangilash kerak emas.

---

## 7. Xodimlarni qo'shish

**Admin panel orqali:** `http://.../admin/employees` → «Xodim qo'shish».

Telegram akkauntini bog'lashning ikki yo'li bor:

* **Oson yo'l:** «Telegram username» maydoniga xodimning username'ini yozib
  qo'yasiz (masalan `aziz_aliyev`). Xodim botga `/start` yozgan zahoti tizim
  uni o'zi bog'laydi.
* **Aniq yo'l:** xodim botga `/start` yozadi, bot uning raqamini ko'rsatadi
  (`123456789`) — shu raqamni «Telegram user_id» maydoniga kiritasiz.

**Terminal orqali:**

```bash
docker compose run --rm web python manage.py add-employee \
  --name "Aliyev Aziz" --position "Menejer" \
  --salary 10000000 --username aziz_aliyev --hired 2026-01-15
```

Keyin `/admin/settings` da:
* **Ish jadvali** — boshlanish/tugash vaqti, tushlik, *grace* muhlati, ish kunlari
* **Ta'til/kasallik** — xodim ta'tilga chiqqanda shu yerdan belgilaysiz

**Bayramlarni** esa bitta buyruq bilan qo'shish mumkin:

```bash
docker compose run --rm web python manage.py holidays --year 2026
```

Qat'iy sanalar o'zi qo'shiladi. Buyruq **qo'lda kiritish kerak bo'lganlarini
ham aytadi**: Ramazon va Qurbon hayiti (aniq kunini O'zbekiston musulmonlari
idorasi e'lon qiladi) va dam olish kuniga tushib qolgan bayramlarning
ko'chirilgan kunlari.

---

## 7a. Avval demo bilan tanishib chiqish (ixtiyoriy)

Bot tokeni yoki xodimlar ro'yxati hali tayyor bo'lmasa, tizimni namunaviy
ma'lumot bilan ko'rib chiqing:

```bash
docker compose run --rm web python manage.py demo --period 2026-07
```

6 ta soxta xodim va bir oylik davomat yaratiladi (kechikadigan, erta
ketadigan, kelmaydigan — har xil). `/admin`, `/admin/payroll` va Excel
eksportini sinab ko'rasiz.

> ⚠️ Bu **soxta ma'lumot**. Haqiqiy ishni boshlashdan oldin bazani tozalang:
> Variant A da `data/tabel.db` faylini o'chirib, `manage.py init` ni qayta
> ishlatish yetarli.

---

## 8. Kunlik ishlash tartibi

| Kim | Nima qiladi |
|---|---|
| Xodim | Kelganda va ketganda QR ni skanerlaydi. `/holat` — bugungi davomati, `/oylik` — shu oydagi hisobi |
| Admin | `/admin` — kunlik jadval. Telefoni bo'lmagan xodim uchun «Qo'lda qayd kiritish» |
| Buxgalter | Oy oxirida `/admin/payroll` → «Oylik .xlsx» va «Tabel .xlsx» |

Oy yopilgach «Bu oyni muhrlab qo'yish» tugmasini bossangiz, hisob natijasi
saqlanadi — keyinchalik davomat tuzatilsa ham muhrlangan summa o'zgarmaydi.

---

## 9. Xizmat ko'rsatish

```bash
# Loglar
docker compose logs -f bot
docker compose logs -f web

# Yangilanish
git pull && docker compose up -d --build

# Baza zaxirasi — Variant A (SQLite): shunchaki fayl nusxasi
cp data/tabel.db "backup-$(date +%F).db"

# Baza zaxirasi — Variant B (Postgres)
docker compose exec -T db pg_dump -U tabel tabel | gzip > backup-$(date +%F).sql.gz

# Eski QR tokenlarini tozalash (haftada bir marta yetarli)
docker compose run --rm web python manage.py purge-tokens --hours 48

# Jadval/bayram o'zgargandan keyin davomatni qayta hisoblash
docker compose run --rm web python manage.py recompute --start 2026-07-01 --end 2026-07-31
```

> Variant A da buyruqlarga `-f docker-compose.local.yml` qo'shiladi, masalan:
> `docker compose -f docker-compose.local.yml logs -f bot`

Zaxirani cron'ga qo'shish (Variant A):

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * cd $HOME/tabel && cp data/tabel.db backup-\$(date +\%F).db") | crontab -
```

---

## Nosozliklarni bartaraf etish

| Muammo | Sabab va yechim |
|---|---|
| QR skanerlanganda «QR kodning muddati o'tgan» | Ekran va server soati farq qilyapti. Ikkalasida ham `timedatectl` bilan NTP yoqilganini tekshiring |
| Bot javob bermayapti | `docker compose logs bot` — `BOT_TOKEN` xato bo'lishi mumkin |
| «Siz tizimda ro'yxatdan o'tmagansiz» | Xodimning `telegram_user_id` si kiritilmagan. `/admin/employees` da to'ldiring |
| QR ichidagi havola ishlamayapti | `.env` da `BOT_USERNAME` bo'sh. To'ldirib `docker compose restart web` |
| Kiosk sahifasi 403 qaytaryapti | Ofisning IP ro'yxati to'ldirilgan, lekin nginx `X-Forwarded-For` bermayapti (5-bo'limga qarang) |
| Kiosk havolasi xodimlarga tarqab ketdi | `/admin/settings` → «Kalitni yangilash». Eski havola darhol ishlamay qoladi |
| Oylik noto'g'ri chiqyapti | Ish jadvali, bayramlar va ta'tillar to'g'ri kiritilganini tekshiring, so'ng `manage.py recompute` |
