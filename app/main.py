"""FastAPI ilovasi: ofis ekrani uchun QR sahifasi + admin panel."""

from __future__ import annotations

import io
import ipaddress
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from pathlib import Path

import qrcode
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from qrcode.image.svg import SvgPathImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance as att_mod
from app import excel as excel_mod
from app import payroll as payroll_mod
from app import security
from app.config import settings
from app.db import get_db, init_db
from app.models import (
    Attendance,
    AttendanceEvent,
    DayStatus,
    Employee,
    EventSource,
    EventType,
    Holiday,
    Kiosk,
    Leave,
    LeaveKind,
    Location,
    Schedule,
)
from app.timeutil import (
    UZ_WEEKDAYS,
    current_period,
    fmt_minutes,
    fmt_time,
    now_local,
    today_local,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        # Serverless muhitda buni o'chirib qo'yiladi: har bir "sovuq start" da
        # jadval yaratishga urinish keraksiz, bir vaqtda bir nechtasi ishga
        # tushsa esa poyga holati chiqadi. U yerda `manage.py init` bir marta.
        init_db()

    if settings.is_public:
        # Internetga chiqarilgan bo'lsa — zaif sozlamalar bilan ishga tushmaymiz.
        # Panelda oyliklar ko'rinadi, «keyin o'zgartiraman» bu yerda ishlamaydi.
        problems = settings.deployment_problems()
        if problems:
            details = "\n  - ".join(problems)
            raise RuntimeError(
                "Internetga chiqarish uchun sozlamalar yetarli emas:\n  - " + details
            )
        log.info("public rejim: %s", settings.public_base_url)

    yield


app = FastAPI(
    title="Davomat va oylik tizimi", docs_url=None, redoc_url=None, lifespan=lifespan
)
# Absolyut yo'l: bulutda ilova boshqa papkadan ishga tushishi mumkin va
# nisbiy yo'l ("app/templates") shablonlarni topolmay qoladi.
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["soat"] = fmt_time
templates.env.filters["daqiqa"] = fmt_minutes
basic_auth = HTTPBasic()

STATUS_LABELS = {
    DayStatus.PRESENT: ("Vaqtida", "ok"),
    DayStatus.LATE: ("Kechikdi", "warn"),
    DayStatus.ABSENT: ("Kelmadi", "bad"),
    DayStatus.LEAVE: ("Ta'til/ruxsat", "info"),
    DayStatus.HOLIDAY: ("Dam olish", "muted"),
    DayStatus.INCOMPLETE: ("Ketishi yo'q", "warn"),
}

EVENT_LABELS = {
    EventType.IN: "Keldi",
    EventType.LUNCH_OUT: "Tushlikka",
    EventType.LUNCH_IN: "Tushlikdan",
    EventType.OUT: "Ketdi",
}


# --------------------------------------------------------------------------- #
# Admin autentifikatsiyasi
# --------------------------------------------------------------------------- #


def require_admin(credentials: HTTPBasicCredentials = Depends(basic_auth)) -> str:
    user_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login yoki parol xato",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --------------------------------------------------------------------------- #
# Kiosk (ofis ekrani)
# --------------------------------------------------------------------------- #


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _ip_allowed(location: Location, client_ip: str) -> bool:
    """Lokatsiyada IP ro'yxati bo'lsa, kiosk sahifasi faqat shu IP'lardan ochiladi.

    DIQQAT: bu faqat **ekranni** himoyalaydi. Skanerlash Telegram orqali kelgani
    uchun xodimning IP'si ko'rinmaydi — jismoniy hozirlik tokenning qisqa
    muddati bilan ta'minlanadi, IP bilan emas.
    """
    allow = (location.ip_allowlist or "").strip()
    if not allow:
        return True
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allow.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


def _get_kiosk(db: Session, api_key: str, request: Request) -> Kiosk:
    kiosk = db.scalars(
        select(Kiosk).where(Kiosk.api_key == api_key, Kiosk.is_active.is_(True))
    ).first()
    if kiosk is None:
        # Mavjud bo'lmagan kalit va o'chirilgan kiosk bir xil javob beradi.
        raise HTTPException(status_code=404, detail="Kiosk topilmadi")
    if not _ip_allowed(kiosk.location, _client_ip(request)):
        raise HTTPException(status_code=403, detail="Bu tarmoqdan ruxsat yo'q")
    return kiosk


@app.get("/kiosk/{api_key}", response_class=HTMLResponse)
def kiosk_page(api_key: str, request: Request, db: Session = Depends(get_db)):
    kiosk = _get_kiosk(db, api_key, request)
    kiosk.last_seen_at = now_local()
    db.commit()
    return templates.TemplateResponse(
        request,
        "kiosk.html",
        {
            "kiosk": kiosk,
            "api_key": api_key,
            "refresh_seconds": settings.qr_refresh_seconds,
            # QR faqat username to'g'ri bo'lsa chiziladi — aks holda kod
            # skanerlanadi-yu hech qayerga olib bormaydi.
            "bot_configured": bool(security.clean_username(settings.bot_username)),
            "bot_username_raw": settings.bot_username.strip(),
            "bot_username_clean": security.clean_username(settings.bot_username),
        },
    )


@app.get("/kiosk/{api_key}/qr.svg")
def kiosk_qr(api_key: str, request: Request, db: Session = Depends(get_db)):
    """Yangi imzolangan token bilan QR rasmi. Har so'rovda yangi token."""
    kiosk = _get_kiosk(db, api_key, request)
    kiosk.last_seen_at = now_local()
    db.commit()

    token = security.issue_token(kiosk.location_id)
    payload = security.deep_link(token)
    if not payload:
        # Buzuq havolali QR chizmaymiz: u ishlayotgandek ko'rinadi, lekin
        # skanerlaganda hech narsa bo'lmaydi va sababini topish qiyin.
        raise HTTPException(
            status_code=503,
            detail="BOT_USERNAME sozlanmagan yoki xato — QR yasab bo'lmaydi",
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=2,
        image_factory=SvgPathImage,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    buffer = io.BytesIO()
    qr.make_image().save(buffer)
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


# --------------------------------------------------------------------------- #
# Admin: kunlik jadval
# --------------------------------------------------------------------------- #


@app.get("/")
def root():
    return RedirectResponse("/admin")


@app.get("/healthz")
def healthz():
    return {"ok": True, "time": now_local().isoformat()}


# --------------------------------------------------------------------------- #
# Telegram webhook
# --------------------------------------------------------------------------- #


@app.post("/telegram/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """Telegram yuborgan yangilanishni qabul qiladi.

    IKKI QAVAT HIMOYA — ikkalasi ham kerak:
      1. yo'ldagi maxfiy qism (`/telegram/<secret>`) — tasodifiy so'rovlar
         umuman bu yergacha yetib kelmaydi;
      2. `X-Telegram-Bot-Api-Secret-Token` sarlavhasi — havola qandaydir yo'l
         bilan oshkor bo'lsa ham, begona so'rov rad etiladi.

    Ikkalasi ham `compare_digest` bilan solishtiriladi.
    """
    # Token yoki maxfiy kalit bo'lmasa endpoint umuman ishlamaydi — 404.
    # BOT_TOKEN tekshiruvi shu yerda bo'lishi muhim: `build_bot()` uni topmasa
    # istisno tashlaydi, u esa 500 ga aylanadi, Telegram esa 500 olgan xabarni
    # to'xtovsiz qayta yuboraveradi.
    if not settings.webhook_secret or not settings.bot_token:
        raise HTTPException(status_code=404, detail="Webhook sozlanmagan")

    header = request.headers.get("x-telegram-bot-api-secret-token", "")
    path_ok = secrets.compare_digest(secret, settings.webhook_secret)
    header_ok = secrets.compare_digest(header, settings.webhook_secret)
    if not (path_ok and header_ok):
        # Sabab aytilmaydi: yo'l xatomi yoki sarlavhami — bu ma'lumot beradi.
        raise HTTPException(status_code=404, detail="Topilmadi")

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="JSON o'qilmadi") from exc

    from app import bot as bot_mod

    # Bot yasash ham `try` ichida: har qanday xato 500 ga aylanmasligi kerak.
    bot = None
    try:
        bot = bot_mod.build_bot()
        await bot_mod.handle_webhook_update(bot, payload)
    except Exception:  # noqa: BLE001
        # Telegram xato javob olsa, o'sha yangilanishni qayta-qayta yuboradi.
        # Bitta buzuq xabar tufayli navbat tiqilib qolmasligi uchun 200 qaytaramiz,
        # lekin logga to'liq yozamiz.
        log.exception("webhook yangilanishini qayta ishlashda xato")
    finally:
        if bot is not None:
            await bot.session.close()

    return {"ok": True}


@app.get("/admin", response_class=HTMLResponse)
def admin_day(
    request: Request,
    day: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    target = date.fromisoformat(day) if day else today_local()
    employees = db.scalars(
        select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.full_name)
    ).all()
    records = {
        row.employee_id: row
        for row in db.scalars(select(Attendance).where(Attendance.work_date == target)).all()
    }

    rows = []
    for emp in employees:
        record = records.get(emp.id)
        if record is None:
            # Ko'rsatish uchun bo'sh xulosa yasaymiz (bazaga yozmaymiz).
            label, tone = ("Kelmadi", "bad")
            if not emp.schedule.is_work_day(target) or att_mod.is_holiday(db, target):
                label, tone = ("Dam olish", "muted")
            elif att_mod.leave_for(db, emp.id, target):
                label, tone = ("Ta'til/ruxsat", "info")
            rows.append(
                {
                    "employee": emp,
                    "record": None,
                    "label": label,
                    "tone": tone,
                }
            )
            continue
        label, tone = STATUS_LABELS.get(record.status, (record.status.value, "muted"))
        rows.append({"employee": emp, "record": record, "label": label, "tone": tone})

    summary = {
        "jami": len(rows),
        "keldi": sum(1 for r in rows if r["record"] and r["record"].check_in_at),
        "kechikdi": sum(
            1 for r in rows if r["record"] and r["record"].billable_late_minutes > 0
        ),
        "kelmadi": sum(1 for r in rows if r["tone"] == "bad"),
    }

    events = db.scalars(
        select(AttendanceEvent)
        .where(AttendanceEvent.work_date == target)
        .order_by(AttendanceEvent.happened_at.desc())
        .limit(60)
    ).all()

    return templates.TemplateResponse(
        request,
        "admin_day.html",
        {
            "day": target,
            "weekday": UZ_WEEKDAYS[target.isoweekday()],
            "rows": rows,
            "summary": summary,
            "events": events,
            "event_labels": EVENT_LABELS,
            "employees": employees,
            "event_types": list(EventType),
        },
    )


@app.post("/admin/manual")
def admin_manual_event(
    employee_id: int = Form(...),
    event_type: str = Form(...),
    happened_at: str = Form(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    """Qo'lda qayd kiritish — bot ishlamay qolgan yoki telefon olmagan holat uchun."""
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    try:
        moment = datetime.fromisoformat(happened_at)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Vaqt formati xato") from exc

    att_mod.record_event(
        db,
        employee,
        EventType(event_type),
        moment,
        source=EventSource.MANUAL,
        note=note,
    )
    att_mod.log_audit(
        db,
        actor,
        "manual_event",
        "employee",
        employee.id,
        f"{event_type} @ {moment.isoformat()} — {note}",
    )
    db.commit()
    return RedirectResponse(f"/admin?day={moment.date().isoformat()}", status_code=303)


@app.post("/admin/events/{event_id}/void")
def admin_void_event(
    event_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    event = db.get(AttendanceEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Yozuv topilmadi")
    day = event.work_date
    att_mod.void_event(db, event_id, actor, "admin bekor qildi")
    db.commit()
    return RedirectResponse(f"/admin?day={day.isoformat()}", status_code=303)


# --------------------------------------------------------------------------- #
# Admin: xodimlar
# --------------------------------------------------------------------------- #


@app.get("/admin/employees", response_class=HTMLResponse)
def admin_employees(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "admin_employees.html",
        {
            "employees": db.scalars(select(Employee).order_by(Employee.full_name)).all(),
            "schedules": db.scalars(select(Schedule).order_by(Schedule.name)).all(),
            "locations": db.scalars(select(Location).order_by(Location.name)).all(),
        },
    )


@app.post("/admin/employees")
def admin_employee_save(
    employee_id: str = Form(""),
    full_name: str = Form(...),
    position: str = Form(""),
    telegram_user_id: str = Form(""),
    telegram_username: str = Form(""),
    monthly_salary: float = Form(0),
    schedule_id: int = Form(...),
    location_id: str = Form(""),
    hired_at: str = Form(""),
    is_active: str = Form("on"),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    employee = db.get(Employee, int(employee_id)) if employee_id else None
    created = employee is None
    if employee is None:
        employee = Employee(full_name=full_name, schedule_id=schedule_id)
        db.add(employee)

    employee.full_name = full_name
    employee.position = position
    employee.telegram_user_id = int(telegram_user_id) if telegram_user_id.strip() else None
    employee.telegram_username = telegram_username.strip().lstrip("@")
    employee.monthly_salary = monthly_salary
    employee.schedule_id = schedule_id
    employee.location_id = int(location_id) if location_id.strip() else None
    employee.hired_at = date.fromisoformat(hired_at) if hired_at.strip() else None
    employee.is_active = is_active == "on"

    db.flush()
    att_mod.log_audit(
        db,
        actor,
        "create_employee" if created else "update_employee",
        "employee",
        employee.id,
        full_name,
    )
    db.commit()
    return RedirectResponse("/admin/employees", status_code=303)


# --------------------------------------------------------------------------- #
# Admin: jadval, bayram, ta'til
# --------------------------------------------------------------------------- #


@app.get("/admin/settings", response_class=HTMLResponse)
def admin_settings(
    request: Request,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "admin_settings.html",
        {
            "schedules": db.scalars(select(Schedule).order_by(Schedule.name)).all(),
            "locations": db.scalars(select(Location).order_by(Location.name)).all(),
            "kiosks": db.scalars(select(Kiosk).order_by(Kiosk.name)).all(),
            "holidays": db.scalars(select(Holiday).order_by(Holiday.day)).all(),
            "leaves": db.scalars(select(Leave).order_by(Leave.start_date.desc())).all(),
            "employees": db.scalars(
                select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.full_name)
            ).all(),
            "leave_kinds": list(LeaveKind),
            "qr_ttl": settings.qr_ttl_seconds,
            "qr_refresh": settings.qr_refresh_seconds,
        },
    )


@app.post("/admin/schedules")
def admin_schedule_save(
    schedule_id: str = Form(""),
    name: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    lunch_start: str = Form(""),
    lunch_end: str = Form(""),
    lunch_minutes: int = Form(60),
    work_days: str = Form("1,2,3,4,5"),
    grace_minutes: int = Form(5),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    schedule = db.get(Schedule, int(schedule_id)) if schedule_id else None
    if schedule is None:
        schedule = Schedule(name=name, start_time=time(9, 0), end_time=time(18, 0))
        db.add(schedule)

    schedule.name = name
    schedule.start_time = time.fromisoformat(start_time)
    schedule.end_time = time.fromisoformat(end_time)
    schedule.lunch_start = time.fromisoformat(lunch_start) if lunch_start.strip() else None
    schedule.lunch_end = time.fromisoformat(lunch_end) if lunch_end.strip() else None
    schedule.lunch_minutes = lunch_minutes
    schedule.work_days = work_days.replace(" ", "")
    schedule.grace_minutes = grace_minutes

    db.flush()
    att_mod.log_audit(db, actor, "save_schedule", "schedule", schedule.id, name)
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/locations")
def admin_location_save(
    name: str = Form(...),
    ip_allowlist: str = Form(""),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    location = Location(name=name, ip_allowlist=ip_allowlist.strip())
    db.add(location)
    db.flush()
    if location.id > 255:
        # QR token formatida location_id 1 bayt (models/security izohiga qarang).
        db.rollback()
        raise HTTPException(status_code=400, detail="Lokatsiyalar soni 255 tadan oshmasligi kerak")
    att_mod.log_audit(db, actor, "create_location", "location", location.id, name)
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/kiosks")
def admin_kiosk_save(
    name: str = Form(...),
    location_id: int = Form(...),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    kiosk = Kiosk(name=name, location_id=location_id, api_key=security.new_api_key())
    db.add(kiosk)
    db.flush()
    att_mod.log_audit(db, actor, "create_kiosk", "kiosk", kiosk.id, name)
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/kiosks/{kiosk_id}/rotate")
def admin_kiosk_rotate(
    kiosk_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    """Kiosk havolasi tarqab ketgan bo'lsa — kalitni yangilash."""
    kiosk = db.get(Kiosk, kiosk_id)
    if kiosk is None:
        raise HTTPException(status_code=404, detail="Kiosk topilmadi")
    kiosk.api_key = security.new_api_key()
    att_mod.log_audit(db, actor, "rotate_kiosk_key", "kiosk", kiosk.id, kiosk.name)
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/holidays")
def admin_holiday_save(
    day: str = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    target = date.fromisoformat(day)
    holiday = db.get(Holiday, target)
    if holiday is None:
        db.add(Holiday(day=target, name=name))
    else:
        holiday.name = name
    att_mod.log_audit(db, actor, "save_holiday", "holiday", day, name)
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


@app.post("/admin/leaves")
def admin_leave_save(
    employee_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    kind: str = Form(...),
    is_paid: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise HTTPException(status_code=400, detail="Tugash sanasi boshlanishdan oldin")

    leave = Leave(
        employee_id=employee_id,
        start_date=start,
        end_date=end,
        kind=LeaveKind(kind),
        is_paid=is_paid == "on",
        note=note,
    )
    db.add(leave)
    db.flush()
    # Ta'til statuslari kunlik xulosalarda ko'rinishi uchun qayta hisoblaymiz.
    att_mod.recompute_range(db, employee, start, end)
    att_mod.log_audit(db, actor, "create_leave", "leave", leave.id, f"{start}..{end} {kind}")
    db.commit()
    return RedirectResponse("/admin/settings", status_code=303)


# --------------------------------------------------------------------------- #
# Admin: oylik
# --------------------------------------------------------------------------- #


@app.get("/admin/payroll", response_class=HTMLResponse)
def admin_payroll(
    request: Request,
    period: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    target = period or current_period()
    results = payroll_mod.compute_period(db, target)
    totals = {
        "salary": sum(r.monthly_salary for r in results),
        "unpaid": sum(r.unpaid_time_deduction for r in results),
        "bonus": sum(r.bonus_reduction for r in results),
        "net": sum(r.net_payable for r in results),
    }
    return templates.TemplateResponse(
        request,
        "admin_payroll.html",
        {"period": target, "results": results, "totals": totals},
    )


@app.post("/admin/payroll/save")
def admin_payroll_save(
    period: str = Form(...),
    db: Session = Depends(get_db),
    actor: str = Depends(require_admin),
):
    """Oylik hisobini `payroll_items` ga muhrlab qo'yish."""
    results = payroll_mod.compute_period(db, period)
    payroll_mod.save_results(db, results)
    att_mod.log_audit(db, actor, "save_payroll", "period", period, f"{len(results)} xodim")
    db.commit()
    return RedirectResponse(f"/admin/payroll?period={period}", status_code=303)


@app.get("/admin/payroll.xlsx")
def admin_payroll_xlsx(
    period: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    target = period or current_period()
    content = excel_mod.payroll_workbook(payroll_mod.compute_period(db, target), target)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="oylik-{target}.xlsx"'},
    )


@app.get("/admin/tabel.xlsx")
def admin_tabel_xlsx(
    period: str | None = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    target = period or current_period()
    content = excel_mod.attendance_workbook(db, target)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="tabel-{target}.xlsx"'},
    )
