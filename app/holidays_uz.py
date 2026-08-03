"""O'zbekiston Respublikasining nishonlanadigan sanalari.

IKKI TOIFA — VA NEGA BU MUHIM
-----------------------------
1. **Qat'iy sanalar** — har yili bir xil kunga to'g'ri keladi. Bularni tizim
   o'zi qo'shadi (`manage.py holidays --year 2026`).

2. **Ko'chib yuruvchi sanalar** — Ramazon hayiti va Qurbon hayiti oy taqvimiga
   bog'langan. Ularning **aniq kunini O'zbekiston musulmonlari idorasi e'lon
   qiladi**, astronomik hisob esa bir kunga farq qilishi mumkin. Shu sababli
   tizim ularni O'ZI QO'SHMAYDI — faqat taxminiy sanani eslatib, qo'lda
   tasdiqlashni so'raydi. Oylik hisobi shu kunlarga bog'liq bo'lgani uchun
   taxminiy sanani "haqiqat" deb yozib qo'yish xato bo'lardi.

Bundan tashqari: bayram shanba yoki yakshanbaga tushsa, dam olish kuni boshqa
kunga **ko'chiriladi** — buni har yili Vazirlar Mahkamasi qarori belgilaydi.
Uni ham qo'lda kiritish kerak (admin panel -> Sozlamalar -> Bayramlar).
"""

from __future__ import annotations

from datetime import date

# (oy, kun, nomi) — har yili o'zgarmaydigan bayramlar
FIXED_HOLIDAYS: list[tuple[int, int, str]] = [
    (1, 1, "Yangi yil"),
    (1, 14, "Vatan himoyachilari kuni"),
    (3, 8, "Xotin-qizlar kuni"),
    (3, 21, "Navro'z bayrami"),
    (5, 9, "Xotira va qadrlash kuni"),
    (9, 1, "Mustaqillik kuni"),
    (10, 1, "O'qituvchi va murabbiylar kuni"),
    (12, 8, "O'zbekiston Respublikasi Konstitutsiyasi kuni"),
]

# Oy taqvimiga bog'liq bayramlar — TAXMINIY sanalar, tasdiqlash shart.
# Manba: astronomik hisob. Rasmiy sana har yili alohida e'lon qilinadi.
LUNAR_HOLIDAYS_APPROX: dict[int, list[tuple[date, str]]] = {
    2026: [
        (date(2026, 3, 20), "Ramazon hayiti (taxminiy)"),
        (date(2026, 5, 27), "Qurbon hayiti (taxminiy)"),
    ],
    2027: [
        (date(2027, 3, 10), "Ramazon hayiti (taxminiy)"),
        (date(2027, 5, 17), "Qurbon hayiti (taxminiy)"),
    ],
}


def fixed_for_year(year: int) -> list[tuple[date, str]]:
    """Berilgan yil uchun qat'iy bayramlar ro'yxati."""
    return [(date(year, month, day), name) for month, day, name in FIXED_HOLIDAYS]


def lunar_hints_for_year(year: int) -> list[tuple[date, str]]:
    """Qo'lda tasdiqlash kerak bo'lgan bayramlarning taxminiy sanalari."""
    return list(LUNAR_HOLIDAYS_APPROX.get(year, []))


def weekend_collisions(year: int) -> list[tuple[date, str]]:
    """Dam olish kuniga tushib qolgan bayramlar.

    Bunday holatda dam olish kuni boshqa kunga ko'chiriladi — buni admin qo'lda
    kiritadi, chunki ko'chirish sanasini har yili hukumat qarori belgilaydi.
    """
    return [
        (day, name) for day, name in fixed_for_year(year) if day.isoweekday() in (6, 7)
    ]
