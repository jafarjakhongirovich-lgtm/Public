#!/usr/bin/env bash
# macOS / Linux: ./start.sh
# Python'ni topib, start.py ga hamma ishni topshiradi.

cd "$(dirname "$0")" || exit 1

for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    exec "$candidate" start.py "$@"
  fi
done

cat <<'MSG'

 [!] Python topilmadi.

 macOS:  brew install python@3.12
 Ubuntu: sudo apt install python3 python3-venv
 Yoki:   https://www.python.org/downloads/

MSG
exit 1
