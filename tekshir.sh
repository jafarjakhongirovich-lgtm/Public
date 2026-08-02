#!/usr/bin/env bash
# QR ishlamayotgan bo'lsa: ./tekshir.sh
# QR ichida aynan qanday havola borligini ko'rsatadi.
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo
    echo "  [!] Tizim hali o'rnatilmagan. Avval ./start.sh ni ishga tushiring."
    echo
    exit 1
fi

.venv/bin/python manage.py qr-check
