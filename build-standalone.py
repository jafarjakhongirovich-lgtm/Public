#!/usr/bin/env python3
"""Собирает сайт в один самодостаточный HTML-файл (dist/machos.html).

Three.js и RoomEnvironment встраиваются прямо в страницу, importmap убирается.
Такой файл открывается двойным кликом и работает без интернета — удобно
отправить заказчику или положить на любой хостинг одним файлом.

Запуск:  python3 build-standalone.py
"""
import re, os

three = open('vendor/three/three.module.min.js').read()
room  = open('vendor/three/addons/environments/RoomEnvironment.js').read()
html  = open('index.html').read()

# из списка экспортов three собираем объект THREE — код сайта обращается к нему
clause = list(re.finditer(r'export\s*\{([^}]*)\}\s*;?\s*$', three.strip()))[-1].group(1)
pairs = []
for part in clause.split(','):
    part = part.strip()
    if not part:
        continue
    local, pub = ([x.strip() for x in part.split(' as ')] if ' as ' in part else (part, part))
    pairs.append((pub, local))
three_ns = 'const THREE={' + ','.join(f'{pub}:{local}' for pub, local in pairs) + '};'

# RoomEnvironment берёт зависимости из THREE и перестаёт быть отдельным модулем
im = re.search(r'import\s*\{([^}]*)\}\s*from\s*[\'"]three[\'"]\s*;?', room)
names = [n.strip() for n in im.group(1).split(',') if n.strip()]
room_body = room.replace(im.group(0), 'const {' + ', '.join(names) + '} = THREE;')
room_body = re.sub(r'\bexport\s+\{[^}]*\}\s*;?', '', room_body)
room_body = re.sub(r'\bexport\s+(class|const|function)\b', r'\1', room_body)

html = re.sub(r'<script type="importmap">.*?</script>\s*', '', html, flags=re.S)

# Фотографии кладём внутрь файла: одиночная страница не может дотянуться
# до папки assets, и вместо картинок остаются пустые рамки.
import base64, glob
assets = {}
for f in sorted(glob.glob('assets/*')):
    ext = os.path.splitext(f)[1].lower()
    mime = {'.jpg':'image/jpeg', '.jpeg':'image/jpeg',
            '.png':'image/png', '.webp':'image/webp'}.get(ext)
    if not mime:
        continue
    with open(f, 'rb') as fh:
        assets[f] = f'data:{mime};base64,' + base64.b64encode(fh.read()).decode()
if assets:
    inline = ('<script>window.__ASSETS = {'
              + ','.join(f'{k!r}:{v!r}' for k, v in assets.items())
              + '};</script>\n')
    html = html.replace('<script type="module">', inline + '<script type="module">', 1)
    print(f'встроено фотографий: {len(assets)}')

OLD_HEAD = """<script type="module">
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';"""
assert OLD_HEAD in html, 'не найдено начало модуля — проверьте index.html'

# код сайта живёт в собственном блоке: иначе его имена сталкиваются с именами
# из минифицированной сборки three, попавшей в ту же область видимости
new_head = ('<script type="module">\n'
            '/* ---- Three.js r169 (MIT) ---- */\n' + three + '\n' + three_ns +
            '\n/* ---- RoomEnvironment (MIT) ---- */\n' + room_body +
            '\n/* ---- сайт ---- */\n{')
html = html.replace(OLD_HEAD, new_head, 1)

MARKER = '\nwindow.__machosBooted = true;'
assert MARKER in html
end = html.index('</script>', html.index(MARKER))
html = html[:end] + '}\n' + html[end:]

os.makedirs('dist', exist_ok=True)
with open('dist/machos.html', 'w') as f:
    f.write(html)
print(f'dist/machos.html — {len(html) / 1024:.0f} KB')
