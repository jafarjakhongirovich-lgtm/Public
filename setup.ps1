#Requires -Version 5.1
<#
    Jarvis — автоматическая установка.
    Запускается двойным щелчком по install.bat.

    Делает всё, что иначе пришлось бы набирать руками:
    проверяет Node.js и Python, ставит Claude Code, выполняет вход по подписке,
    ставит зависимости бота, узнаёт ваш Telegram ID и записывает настройки.
#>

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
# Windows PowerShell 5.1 по умолчанию пробует TLS 1.0 — api.telegram.org откажет.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

Set-Location -LiteralPath $PSScriptRoot

function Say([string]$text, [string]$color = 'Gray') { Write-Host $text -ForegroundColor $color }
function Step([int]$n, [string]$text) { Write-Host ''; Say ">>> Шаг $n из 7. $text" 'Cyan' }
function Ok([string]$text) { Say "    Готово: $text" 'Green' }

function Stop-With([string]$problem, [string]$howto) {
    Write-Host ''
    Say '========================================' 'Red'
    Say "НЕ ПОЛУЧИЛОСЬ: $problem" 'Red'
    Write-Host ''
    Say $howto 'Yellow'
    Say '========================================' 'Red'
    Write-Host ''
    Read-Host 'Нажмите Enter, чтобы закрыть окно'
    exit 1
}

Write-Host ''
Say '=====================================' 'Cyan'
Say '   Jarvis - установка' 'Cyan'
Say '=====================================' 'Cyan'
Say 'Ничего нажимать не нужно, пока не попрошу.'

# --- Шаг 1: базовые программы -------------------------------------------------

Step 1 'Проверяю Node.js и Python'

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Stop-With 'Node.js не установлен.' @'
Откройте nodejs.org, нажмите "Get Node.js", скачайте и установите.
Затем ЗАКРОЙТЕ это окно и запустите install.bat заново.
'@
}
Ok "Node.js $(node -v)"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Stop-With 'Python не установлен.' @'
Откройте python.org/downloads, скачайте и установите Python.
Затем ЗАКРОЙТЕ это окно и запустите install.bat заново.
'@
}
Ok "Python $(python --version)"

# --- Шаг 2: Claude Code -------------------------------------------------------

Step 2 'Устанавливаю Claude Code (примерно минута)'

# npm.cmd, а не npm: обходит запрет Windows на запуск .ps1-скриптов.
# --allow-scripts обязателен: без него npm пропускает postinstall,
# и Claude Code остаётся установленным лишь наполовину.
& npm.cmd install -g '--allow-scripts=@anthropic-ai/claude-code' '@anthropic-ai/claude-code' 2>&1 |
    ForEach-Object { Say "    $_" 'DarkGray' }
if ($LASTEXITCODE -ne 0) {
    Stop-With 'Не удалось установить Claude Code.' @'
Проверьте подключение к интернету и запустите install.bat ещё раз.
'@
}

# После установки claude может быть ещё не виден в PATH этого окна —
# ищем его напрямую в папке, куда npm ставит глобальные программы.
$claude = 'claude'
try {
    $prefix = (& npm.cmd config get prefix 2>$null).Trim()
    $candidate = Join-Path $prefix 'claude.cmd'
    if (Test-Path -LiteralPath $candidate) { $claude = $candidate }
} catch {}

if ($claude -eq 'claude' -and -not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Stop-With 'Claude Code установился, но система его не видит.' @'
Закройте это окно и запустите install.bat заново - обычно после
перезапуска всё находится.
'@
}
Ok 'Claude Code установлен'

# --- Шаг 3: вход по подписке --------------------------------------------------

Step 3 'Вход в ваш аккаунт Claude'

& $claude auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Say '    Сейчас откроется браузер.' 'Yellow'
    Say '    Войдите тем аккаунтом, где оплачена подписка Claude,' 'Yellow'
    Say '    и подтвердите доступ. Потом вернитесь сюда.' 'Yellow'
    Write-Host ''
    & $claude auth login
    if ($LASTEXITCODE -ne 0) {
        Stop-With 'Вход не выполнен.' @'
Запустите install.bat заново и повторите вход в браузере.
'@
    }
}
Ok 'Вход выполнен - бот будет работать на вашей подписке'

# --- Шаг 4: зависимости бота --------------------------------------------------

Step 4 'Устанавливаю сам бот (примерно минута)'

if (-not (Test-Path -LiteralPath '.venv')) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Stop-With 'Не удалось подготовить окружение Python.' 'Запустите install.bat заново.' }
}

$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip --quiet 2>&1 | Out-Null
& $py -m pip install -r requirements.txt --quiet 2>&1 | ForEach-Object { Say "    $_" 'DarkGray' }
if ($LASTEXITCODE -ne 0) {
    Stop-With 'Не удалось установить зависимости бота.' 'Проверьте интернет и запустите install.bat заново.'
}
Ok 'Бот установлен'

# --- Шаг 5: токен и Telegram ID ----------------------------------------------

Step 5 'Подключаю вашего бота в Telegram'

if (Test-Path -LiteralPath '.env') {
    Say '    Файл настроек уже есть.' 'DarkGray'
    $again = Read-Host '    Настроить заново? (д/н)'
    if ($again -notmatch '^[дdyу]') {
        Ok 'Оставляю прежние настройки'
        $skipConfig = $true
    }
}

if (-not $skipConfig) {
    Write-Host ''
    Say '    Если бота ещё нет: откройте в Telegram @BotFather,' 'Yellow'
    Say '    отправьте /newbot и следуйте подсказкам.' 'Yellow'
    Say '    В ответ придёт длинная строка вида 8123456789:AAH...' 'Yellow'
    Write-Host ''

    $bot = $null
    while (-not $bot) {
        $token = (Read-Host '    Вставьте эту строку сюда и нажмите Enter').Trim()
        if (-not $token) { continue }
        try {
            $resp = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getMe" -TimeoutSec 20
            if ($resp.ok) { $bot = $resp.result } else { Say '    Токен не подошёл. Попробуйте ещё раз.' 'Red' }
        } catch {
            Say '    Токен не подошёл или нет интернета. Попробуйте ещё раз.' 'Red'
        }
    }
    Ok "Бот найден: @$($bot.username)"

    Write-Host ''
    Say "    Теперь откройте @$($bot.username) в Telegram," 'Yellow'
    Say '    нажмите Start и отправьте ему любое сообщение.' 'Yellow'
    Say '    Жду...' 'Yellow'

    $ownerId = $null
    $deadline = (Get-Date).AddMinutes(5)
    while (-not $ownerId -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $upd = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates?limit=100" -TimeoutSec 20
            if ($upd.ok -and $upd.result.Count -gt 0) {
                # @(...) — на случай, если пришло ровно одно обновление
                $last = @($upd.result)[-1]
                $from = $null
                if ($last.message) { $from = $last.message.from }
                elseif ($last.edited_message) { $from = $last.edited_message.from }
                if ($from -and -not $from.is_bot) { $ownerId = $from.id; $ownerName = $from.first_name }
            }
        } catch {}
    }

    if (-not $ownerId) {
        Stop-With 'Сообщение от вас так и не пришло.' @'
Убедитесь, что открыли именно своего бота и нажали Start,
затем запустите install.bat заново.
'@
    }
    Ok "Это вы: $ownerName (ID $ownerId). Отвечать бот будет только вам."

    $env_text = @"
TELEGRAM_BOT_TOKEN=$token
JARVIS_OWNER_IDS=$ownerId
JARVIS_WORKSPACE=./workspace
JARVIS_PERMISSION_MODE=acceptEdits
JARVIS_ALLOWED_TOOLS=Read,Write,Edit,Glob,Grep,Bash,WebSearch,WebFetch
JARVIS_SHOW_TOOLS=1
JARVIS_MEMORY_DAYS=0
JARVIS_WHISPER_MODEL=small
JARVIS_TTS_VOICE=ru-RU-DmitryNeural
JARVIS_TTS_MODE=always
JARVIS_EXTRA_DIRS=
"@
    # ASCII, чтобы Windows не подмешал в начало файла невидимые символы.
    Set-Content -LiteralPath '.env' -Value $env_text -Encoding ASCII
    Ok 'Настройки сохранены'
}

# --- Шаг 6: автозапуск --------------------------------------------------------

Step 6 'Запуск вместе с Windows'

$startupLink = Join-Path ([Environment]::GetFolderPath('Startup')) 'Jarvis.lnk'
if (Test-Path -LiteralPath $startupLink) {
    Ok 'Автозапуск уже настроен'
} else {
    $answer = Read-Host '    Запускать Jarvis сам при включении компьютера? (д/н)'
    if ($answer -match '^[дdyу]') {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($startupLink)
        $shortcut.TargetPath       = Join-Path $PSScriptRoot 'start.bat'
        $shortcut.WorkingDirectory = $PSScriptRoot
        $shortcut.WindowStyle      = 7
        $shortcut.Description      = 'Jarvis - личный ассистент в Telegram'
        $shortcut.Save()
        Ok 'Будет запускаться сам при входе в Windows'
    } else {
        Say '    Хорошо. Включить потом - autostart.bat' 'DarkGray'
    }
}

# --- Шаг 7: запуск ------------------------------------------------------------

Step 7 'Запускаю Jarvis'

Write-Host ''
Say '=====================================' 'Green'
Say '   Всё готово!' 'Green'
Say '=====================================' 'Green'
Say 'Пишите боту в Telegram обычным текстом.'
Say ''
Say 'Пока это окно открыто - бот работает.'
Say 'Закроете окно - бот замолчит.'
Say 'Чтобы включить снова - двойной щелчок по start.bat'
Write-Host ''

& $py -m jarvis

Write-Host ''
Read-Host 'Бот остановлен. Нажмите Enter, чтобы закрыть окно'
