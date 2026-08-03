#!/usr/bin/env python3
"""Bir buyruq bilan ishga tushirish.

Nima qiladi:
  1. Python versiyasini tekshiradi (3.11+ kerak)
  2. `.venv` yasaydi va kutubxonalarni o'rnatadi
  3. `.env` yo'q bo'lsa — yaratadi va yangi SECRET_KEY yozadi
  4. Baza yo'q bo'lsa — yaratadi va demo ma'lumot qo'shadi
  5. Havolalarni chiqaradi va web serverni ishga tushiradi

Ishlatish:
    python start.py                # demo ma'lumot bilan (birinchi tanishuv)
    python start.py --no-demo      # bo'sh baza (haqiqiy ish uchun)
    python start.py --port 9000    # boshqa port

Bu fayl TIZIM python'i bilan ishga tushadi va keyingi hamma ishni `.venv`
ichidagi python'ga topshiradi — shuning uchun uni oldin qo'lda sozlash
shart emas.
"""

from __future__ import annotations

import argparse
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
import venv
from pathlib import Path

MIN_PYTHON = (3, 11)
ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


# --------------------------------------------------------------------------- #
# Chiqish
# --------------------------------------------------------------------------- #

_COLOR = sys.stdout.isatty() and platform.system() != "Windows"


def say(text: str = "") -> None:
    print(text, flush=True)


def step(text: str) -> None:
    say(f"\n{'▸' if _COLOR else '>'} {text}")


def ok(text: str) -> None:
    say(f"  {'✓' if _COLOR else '+'} {text}")


def fail(text: str, hint: str = "") -> None:
    say(f"\n{'✗' if _COLOR else '!'} {text}")
    if hint:
        say(f"\n{hint}")
    say("")
    # Windows'da fayl ustiga ikki marta bosilganda oyna darhol yopilib
    # ketmasligi uchun — xato matnini o'qishga imkon beramiz.
    if platform.system() == "Windows" and sys.stdin.isatty():
        input("Davom etish uchun Enter bosing...")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Muhit
# --------------------------------------------------------------------------- #


def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(
            f"Python {'.'.join(map(str, MIN_PYTHON))}+ kerak, "
            f"sizda {platform.python_version()}.",
            "Yangi versiyasini https://www.python.org/downloads/ dan o'rnating.\n"
            "Windows'da o'rnatishda «Add python.exe to PATH» katagini belgilang.",
        )
    ok(f"Python {platform.python_version()}")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv() -> Path:
    python = venv_python()
    if python.exists():
        ok(".venv allaqachon bor")
        return python

    say("  .venv yasalmoqda (bir marta, ~10 sekund)...")
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    except Exception as exc:  # noqa: BLE001
        fail(f".venv yasalmadi: {exc}", "Papkaga yozish huquqi bormi, tekshiring.")
    if not python.exists():
        fail(".venv yasaldi, lekin python topilmadi.")
    ok(".venv tayyor")
    return python


def install_requirements(python: Path) -> None:
    marker = VENV / ".requirements-installed"
    requirements = ROOT / "requirements.txt"
    if not requirements.exists():
        fail(
            "requirements.txt topilmadi.",
            f"Bu fayl loyiha papkasida bo'lishi kerak: {ROOT}\n"
            "Arxivni to'liq chiqarib olganingizni tekshiring.",
        )

    # Fayl o'zgarmagan bo'lsa qayta o'rnatmaymiz — ishga tushirish tez bo'ladi.
    stamp = str(requirements.stat().st_mtime_ns)
    if marker.exists() and marker.read_text().strip() == stamp:
        ok("kutubxonalar o'rnatilgan")
        return

    say("  kutubxonalar o'rnatilmoqda (birinchi marta 1–3 daqiqa)...")
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
         "-r", str(requirements)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        fail(
            "kutubxonalar o'rnatilmadi.",
            "Internet ulanishini tekshiring. Ishlamasa, qo'lda urinib ko'ring:\n"
            f"  {python} -m pip install -r requirements.txt",
        )
    marker.write_text(stamp)
    ok("kutubxonalar o'rnatildi")


def ensure_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        ok(".env allaqachon bor")
        return

    example = ROOT / ".env.example"
    if not example.exists():
        fail(".env.example topilmadi — arxiv to'liq chiqarilmagan.")

    lines = []
    for line in example.read_text(encoding="utf-8").splitlines():
        if line.startswith("SECRET_KEY="):
            line = f"SECRET_KEY={secrets.token_urlsafe(32)}"
        elif line.startswith("ADMIN_PASSWORD="):
            line = "ADMIN_PASSWORD=admin"
        lines.append(line)
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(".env yaratildi, SECRET_KEY yasaldi")


# --------------------------------------------------------------------------- #
# Baza
# --------------------------------------------------------------------------- #


def db_path() -> Path | None:
    """`.env` dagi DATABASE_URL SQLite bo'lsa — fayl yo'lini qaytaradi."""
    env = ROOT / ".env"
    if not env.exists():
        return ROOT / "tabel.db"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL=") and "sqlite" in line:
            raw = line.split("=", 1)[1].strip()
            return Path(raw.split("///")[-1].lstrip("/") if "///" in raw else "tabel.db")
        if line.startswith("DATABASE_URL="):
            return None  # Postgres — o'zi boshqaradi
    return ROOT / "tabel.db"


def run_manage(python: Path, *args: str) -> tuple[int, str]:
    """`manage.py` ni chaqiradi. Chiqishini ushlab qoladi — oxirida bitta
    tartibli xulosa ko'rsatiladi, ikki xil ro'yxat emas."""
    result = subprocess.run(
        [str(python), "manage.py", *args], cwd=ROOT, capture_output=True, text=True
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def ensure_database(python: Path, with_demo: bool) -> bool:
    """Baza tayyorlanadi. Demo qo'shilgan bo'lsa True qaytaradi."""
    path = db_path()
    if path is not None and (ROOT / path).exists():
        ok(f"baza allaqachon bor ({path})")
        return False

    if with_demo:
        say("  baza yasalmoqda va demo ma'lumot qo'shilmoqda...")
        code, output = run_manage(python, "demo")
        if code != 0:
            fail("demo ma'lumot qo'shilmadi.", output.strip())
        ok("demo ma'lumot qo'shildi")
        return True

    say("  baza yasalmoqda...")
    code, output = run_manage(python, "init")
    if code != 0:
        fail("baza yasalmadi.", output.strip())
    ok("bo'sh baza tayyor")
    return False


# --------------------------------------------------------------------------- #
# Havolalar
# --------------------------------------------------------------------------- #


def lan_ip() -> str | None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def kiosk_key(python: Path) -> str | None:
    """Kiosk kalitini bazadan o'qiydi (havolani chiqarish uchun)."""
    code = (
        "from sqlalchemy import select\n"
        "from app.db import session_scope\n"
        "from app.models import Kiosk\n"
        "with session_scope() as db:\n"
        "    k = db.scalars(select(Kiosk)).first()\n"
        "    print(k.api_key if k else '')\n"
    )
    result = subprocess.run(
        [str(python), "-c", code], cwd=ROOT, capture_output=True, text=True
    )
    key = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    return key or None


def qr_link(python: Path) -> str:
    """QR ichiga tushadigan havolani qaytaradi (BOT_USERNAME buzuq bo'lsa — bo'sh).

    Buni har ishga tushganda ekranga chiqaramiz. Sababi: `.env` faqat server
    ko'tarilganda o'qiladi, shuning uchun «tuzatdim, lekin ishlamayapti» holati
    juda oson yuzaga keladi — odam faylni to'g'rilaydi-yu, serverni qayta
    ishga tushirmaydi. Ekrandagi havola esa har doim HOZIRGI holatni ko'rsatadi.
    """
    code = (
        "from app import security\n"
        "print(security.deep_link(security.issue_token(1)))\n"
    )
    result = subprocess.run(
        [str(python), "-c", code], cwd=ROOT, capture_output=True, text=True
    )
    lines = [line for line in result.stdout.strip().splitlines() if line.startswith("https://")]
    return lines[-1] if lines else ""


def bot_username() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("BOT_USERNAME="):
                return line.split("=", 1)[1].strip()
    return ""


def admin_password() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ADMIN_PASSWORD="):
                return line.split("=", 1)[1].strip() or "(bo'sh)"
    return "admin"


def print_links(python: Path, port: int, demo_added: bool) -> None:
    address = lan_ip()
    local = f"http://localhost:{port}"
    say("\n" + "─" * 62)
    say("  TAYYOR — quyidagi havolalarni brauzerda ochasiz")
    say("─" * 62)
    say(f"\n  Admin panel:   {local}/admin")
    say(f"  Login/parol:   admin / {admin_password()}")

    key = kiosk_key(python)
    if key:
        say(f"\n  Ofis ekrani:   {local}/kiosk/{key}")
        if address:
            say(f"  ... tarmoqdan: http://{address}:{port}/kiosk/{key}")
        say("  (bu havola maxfiy — xodimlarga tarqatmang)")

    if demo_added:
        say("\n  Demo ma'lumot qo'shildi: 6 ta soxta xodim va bir oylik davomat.")
        say("  Haqiqiy ishni boshlashda bazani o'chirib, qaytadan ishga tushiring.")

    if not _bot_configured():
        say("\n  Eslatma: BOT_TOKEN va BOT_USERNAME bo'sh, shuning uchun QR ichidagi")
        say("  havola hali ishlamaydi. Panelni ko'rish uchun bu xalal bermaydi.")
        # Papka nusxalanganda yoki arxiv ichma-ich ochilganda odam bir `.env`
        # ni to'ldiradi, server esa boshqasini o'qiydi. To'liq yo'lni yozamiz.
        say(f"  To'ldiriladigan fayl: {ROOT / '.env'}")
    else:
        link = qr_link(python)
        if link:
            say(f"\n  QR ichidagi havola: {link.split('?')[0]}")
            say("  (shu manzilni brauzerda ochib ko'ring — bot sahifasi chiqishi kerak)")
        else:
            raw = bot_username() or "bo'sh"
            say("\n  [!] BOT_USERNAME xato — QR KO'RSATILMAYDI.")
            say(f"      Hozirgi qiymat: «{raw}»")
            say("      U yerga botning ko'rinadigan nomi emas, @ dan keyingi")
            say("      username yoziladi: probelsiz, masalan DavomatTizimiBot.")
            say("      To'g'rilagach shu oynani yopib, qaytadan ishga tushiring.")

    say("\n  To'xtatish uchun: Ctrl+C")
    say("─" * 62 + "\n")


def _bot_configured() -> bool:
    env = ROOT / ".env"
    if not env.exists():
        return False
    text = env.read_text(encoding="utf-8")
    return any(
        line.startswith("BOT_TOKEN=") and len(line.split("=", 1)[1].strip()) > 10
        for line in text.splitlines()
    )


# --------------------------------------------------------------------------- #
# Asosiy
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description="Davomat tizimini ishga tushirish")
    parser.add_argument("--no-demo", action="store_true", help="demo ma'lumotsiz, bo'sh baza")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--setup-only", action="store_true", help="faqat sozlash, serverni ishga tushirmaslik"
    )
    args = parser.parse_args()

    say("Davomat va oylik tizimi — ishga tushirish")
    say(f"Papka: {ROOT}")

    step("Muhitni tekshirish")
    check_python()
    python = ensure_venv()
    install_requirements(python)

    step("Sozlamalar")
    ensure_env()

    step("Baza")
    demo_added = ensure_database(python, with_demo=not args.no_demo)

    print_links(python, args.port, demo_added)

    if args.setup_only:
        say("--setup-only: server ishga tushirilmadi.")
        return

    run_services(python, args.port)


def run_services(python: Path, port: int) -> None:
    """Web serverni va (token bo'lsa) botni birga ishga tushiradi.

    Ikkalasi ALOHIDA jarayon: web server so'rovlarga javob beradi, bot esa
    Telegram'ni doimiy so'rab turadi (long polling). Faqat web serverni ishga
    tushirish yetarli emas — panel ochiladi, lekin bot jim turadi va xodimning
    /start xabariga hech kim javob bermaydi.
    """
    env_file = ROOT / ".env"
    processes: list[tuple[str, subprocess.Popen]] = []

    def spawn() -> None:
        processes.clear()
        web = subprocess.Popen(
            [str(python), "-m", "uvicorn", "app.main:app",
             "--host", "0.0.0.0", "--port", str(port)],
            cwd=ROOT,
        )
        processes.append(("web server", web))

        if _bot_configured():
            bot = subprocess.Popen([str(python), "-m", "app.bot"], cwd=ROOT)
            processes.append(("bot", bot))
            say("  bot ham ishga tushdi (Telegram'ni kutmoqda)")
        else:
            say("  bot ishga tushirilmadi: .env da BOT_TOKEN yo'q")
            say(f"  tokenni brauzerda kiritish mumkin: http://localhost:{port}/admin/setup")

    def stop() -> None:
        for _name, process in processes:
            if process.poll() is None:
                process.terminate()
        for _name, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    def env_stamp() -> float:
        try:
            return env_file.stat().st_mtime
        except OSError:
            return 0.0

    spawn()
    stamp = env_stamp()

    try:
        while True:
            # `.env` o'zgarsa — qayta ishga tushiramiz. Sozlamalar faqat
            # ishga tushganda o'qiladi, shuning uchun bunisiz brauzerdan
            # kiritilgan token botga umuman yetib bormaydi: odam saqlaydi,
            # "tayyor" yozuvini ko'radi, lekin bot jim turaveradi.
            current = env_stamp()
            if current != stamp:
                stamp = current
                say("\n.env o'zgardi — qayta ishga tushirilmoqda...")
                stop()
                spawn()

            # Qaysi biri birinchi to'xtasa — ikkinchisini ham to'xtatamiz, aks
            # holda bot jim o'lib, panel esa ishlayotgandek ko'rinib turadi.
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    say(f"\n{name} to'xtadi (kod {code}).")
                    raise _ServiceStopped
            time.sleep(1)
    except (KeyboardInterrupt, _ServiceStopped):
        pass
    finally:
        stop()
        say("To'xtatildi.")


class _ServiceStopped(Exception):
    """Ichki signal: jarayonlardan biri o'zi to'xtadi."""


if __name__ == "__main__":
    if shutil.which("python") is None and os.name != "nt":
        pass  # tizim python'i bilan ishga tushirilgan, tekshirish shart emas
    main()
