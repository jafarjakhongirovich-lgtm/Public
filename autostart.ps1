<#
    Автозапуск Jarvis вместе с Windows.

    Кладёт ярлык на start.bat в папку автозагрузки пользователя. Это проще и
    честнее службы: бот запускается под вашей учётной записью, а значит видит
    вход в Claude, который к ней и привязан. Служба вошла бы как SYSTEM и
    подписку не нашла бы.
#>
param([switch]$Off)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$startup  = [Environment]::GetFolderPath('Startup')
$link     = Join-Path $startup 'Jarvis.lnk'
$target   = Join-Path $PSScriptRoot 'start.bat'

if ($Off) {
    if (Test-Path -LiteralPath $link) {
        Remove-Item -LiteralPath $link -Force
        Write-Host 'Автозапуск выключен. Jarvis больше не стартует сам.' -ForegroundColor Yellow
    } else {
        Write-Host 'Автозапуск и так был выключен.' -ForegroundColor Gray
    }
    Read-Host 'Нажмите Enter, чтобы закрыть окно'
    exit 0
}

if (-not (Test-Path -LiteralPath $target)) {
    Write-Host 'Не нашёл start.bat рядом с этим файлом.' -ForegroundColor Red
    Write-Host 'Сначала установите бота (install.bat).' -ForegroundColor Yellow
    Read-Host 'Нажмите Enter, чтобы закрыть окно'
    exit 1
}

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath       = $target
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle      = 7          # свернуть в панель задач, чтобы не мешало
$shortcut.Description      = 'Jarvis - личный ассистент в Telegram'
$shortcut.Save()

Write-Host ''
Write-Host 'Готово: Jarvis будет запускаться сам при входе в Windows.' -ForegroundColor Green
Write-Host 'Окно откроется свёрнутым - бот работает, пока оно не закрыто.' -ForegroundColor Gray
Write-Host ''
Write-Host 'Выключить автозапуск: запустите autostart-off.bat' -ForegroundColor Gray
Write-Host ''
Read-Host 'Нажмите Enter, чтобы закрыть окно'
