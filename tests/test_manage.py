"""`manage.py` buyruqlari: ro'yxatdan o'tganmi va tashxis to'g'ri javob beradimi.

Bu yerdagi asosiy tekshiruv — har bir buyruq `func` ga bog'langanligi.
Funksiyani yozib, `build_parser()` da ro'yxatga qo'shishni unutish oson,
va bunday xato faqat foydalanuvchi buyruqni terganda ma'lum bo'ladi.
"""

from __future__ import annotations

import argparse

import pytest

import manage


def _commands() -> dict[str, argparse.ArgumentParser]:
    for action in manage.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise AssertionError("subparser topilmadi")


def test_every_documented_command_is_registered():
    """Modul docstring'ida va'da qilingan har bir buyruq haqiqatan ishlashi kerak."""
    documented = {
        line.split("python manage.py ", 1)[1].split()[0]
        for line in manage.__doc__.splitlines()
        if "python manage.py " in line
    }
    assert documented <= set(_commands())


def test_every_cmd_function_is_reachable():
    """`cmd_*` yozilib, parserga ulanmay qolgan funksiya bo'lmasin."""
    defined = {
        getattr(manage, name)
        for name in dir(manage)
        if name.startswith("cmd_") and callable(getattr(manage, name))
    }
    wired = {parser.get_default("func") for parser in _commands().values()}
    assert defined - wired == set()


def test_qr_check_is_registered():
    args = manage.build_parser().parse_args(["qr-check"])
    assert args.func is manage.cmd_qr_check


def test_qr_check_shows_the_link_inside_the_qr(capsys, monkeypatch):
    monkeypatch.setattr(manage.settings, "bot_username", "TestTabelBot")
    monkeypatch.setattr(manage.settings, "bot_token", "")

    manage.cmd_qr_check(argparse.Namespace())

    out = capsys.readouterr().out
    assert "https://t.me/TestTabelBot?start=" in out
    assert "BOT_TOKEN" in out  # tasdiqlab bo'lmagani aytiladi


def test_qr_check_fails_loudly_on_a_broken_username(capsys, monkeypatch):
    """Probelli nom — aynan shu xato QR ni «ishlamaydigan» qiladi."""
    monkeypatch.setattr(manage.settings, "bot_username", "Davomat tizimi")

    with pytest.raises(SystemExit) as exc:
        manage.cmd_qr_check(argparse.Namespace())

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Davomat tizimi" in out
    assert "XATO" in out
    assert "https://t.me/" not in out  # buzuq havola ko'rsatilmaydi
