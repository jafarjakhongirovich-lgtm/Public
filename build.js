/* Сборка одного самодостаточного index.html из модулей в src/ */
const fs = require('fs');
const path = require('path');

const src = (f) => fs.readFileSync(path.join(__dirname, 'src', f), 'utf8');

const css = src('style.css');
const body = src('body.html');
const js = [src('engine.js'), src('car.js'), src('app.js')].join('\n\n');

const html = `<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="Интерактивная 3D-презентация Porsche 911 GT3 RS (992): полные технические характеристики, аэродинамика, двигатель, шасси и габариты.">
<meta name="color-scheme" content="dark">
<title>Porsche 911 GT3 RS (992) — 3D-презентация</title>
<style>
${css}
</style>
</head>
<body>
${body}
<script>
${js}
</script>
</body>
</html>
`;

fs.writeFileSync(path.join(__dirname, 'index.html'), html);

// Версия для публикации как Artifact: без <html>/<head>/<body> обёртки
const artifact = `<title>Porsche 911 GT3 RS (992) — 3D-презентация</title>
<style>
${css}
</style>
${body}
<script>
${js}
</script>
`;
fs.writeFileSync(path.join(__dirname, 'dist', 'artifact.html'), artifact);

console.log('index.html: ' + (html.length / 1024).toFixed(1) + ' KB');
console.log('dist/artifact.html: ' + (artifact.length / 1024).toFixed(1) + ' KB');
