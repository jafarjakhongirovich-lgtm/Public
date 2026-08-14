<#
    Перенос данных из прошлой установки Jarvis в эту.

    При обновлении бот распаковывается в новую папку, а всё нажитое —
    настройки, память разговора и заметки — остаётся в старой. Этот скрипт
    находит прошлую установку и переносит их сюда.
#>

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Say([string]$t, [string]$c = 'Gray') { Write-Host $t -ForegroundColor $c }

$here = $PSScriptRoot

Write-Host ''
Say '=====================================' 'Cyan'
Say '   Перенос данных из старой версии' 'Cyan'
Say '=====================================' 'Cyan'
Write-Host ''
Say 'Ищу прошлые установки Jarvis...'

# Ищем там, куда обычно попадают распакованные архивы.
$searchRoots = @($HOME, (Join-Path $HOME 'Downloads'), (Join-Path $HOME 'Desktop'), 'C:\') |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique

$found = @()
foreach ($root in $searchRoots) {
    try {
        Get-ChildItem -LiteralPath $root -Directory -Depth 2 -ErrorAction SilentlyContinue |
            ForEach-Object {
                $envFile = Join-Path $_.FullName '.env'
                $marker  = Join-Path $_.FullName 'jarvis\__main__.py'
                if ((Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $marker)) {
                    if ($_.FullName -ne $here) { $found += $_ }
                }
            }
    } catch {}
}

$found = $found | Sort-Object -Property FullName -Unique

if ($found.Count -eq 0) {
    Say 'Прошлых установок не нашёл.' 'Yellow'
    Say 'Если знаете, где лежит старая папка, скопируйте оттуда вручную:' 'Gray'
    Say '  .env, sessions.json и папку workspace' 'Gray'
    Write-Host ''
    Read-Host 'Нажмите Enter, чтобы закрыть окно'
    exit 0
}

if ($found.Count -eq 1) {
    $source = $found[0].FullName
    Say "Нашёл: $source" 'Green'
} else {
    Write-Host ''
    Say 'Нашёл несколько установок:' 'Yellow'
    for ($i = 0; $i -lt $found.Count; $i++) {
        $age = $found[$i].LastWriteTime.ToString('dd.MM.yyyy HH:mm')
        Say ("  [{0}] {1}   (изменена {2})" -f ($i + 1), $found[$i].FullName, $age)
    }
    Write-Host ''
    $pick = Read-Host 'Из какой переносить? Введите номер'
    $index = 0
    if (-not [int]::TryParse($pick, [ref]$index) -or $index -lt 1 -or $index -gt $found.Count) {
        Say 'Не понял номер. Запустите ещё раз.' 'Red'
        Read-Host 'Нажмите Enter, чтобы закрыть окно'
        exit 1
    }
    $source = $found[$index - 1].FullName
}

Write-Host ''
$moved = @()

# Настройки: токен бота, ваш ID, все параметры.
$srcEnv = Join-Path $source '.env'
$dstEnv = Join-Path $here '.env'
if (Test-Path -LiteralPath $srcEnv) {
    if (Test-Path -LiteralPath $dstEnv) {
        Copy-Item -LiteralPath $dstEnv -Destination (Join-Path $here '.env.старый') -Force
    }
    Copy-Item -LiteralPath $srcEnv -Destination $dstEnv -Force
    $moved += 'настройки (.env)'
}

# Память: какой разговор продолжать в каждом чате.
$srcSess = Join-Path $source 'sessions.json'
if (Test-Path -LiteralPath $srcSess) {
    Copy-Item -LiteralPath $srcSess -Destination (Join-Path $here 'sessions.json') -Force
    $moved += 'память разговора'
}

# Рабочая папка: заметки, присланные файлы, готовые документы.
$srcWs = Join-Path $source 'workspace'
$dstWs = Join-Path $here 'workspace'
if (Test-Path -LiteralPath $srcWs) {
    New-Item -ItemType Directory -Path $dstWs -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $srcWs '*') -Destination $dstWs -Recurse -Force -ErrorAction SilentlyContinue
    $moved += 'рабочая папка и заметки'
}

if ($moved.Count -eq 0) {
    Say 'Переносить оказалось нечего.' 'Yellow'
} else {
    Say 'Перенёс:' 'Green'
    foreach ($m in $moved) { Say "  - $m" 'Green' }
    Write-Host ''
    Say 'Старая папка не тронута - можете удалить её сами, когда убедитесь,' 'Gray'
    Say 'что новая версия работает.' 'Gray'
}

Write-Host ''
Say 'Теперь запустите install.bat (или start.bat, если уже установлено).' 'Cyan'
Write-Host ''
Read-Host 'Нажмите Enter, чтобы закрыть окно'
