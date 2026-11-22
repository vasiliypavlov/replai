@echo off
:: Запускаем PowerShell в новом окне
:: -NoExit оставляет окно открытым после завершения скрипта (важно для REPL)
:: Set-Location -LiteralPath '%~dp0' переходит в папку, где лежит этот .bat файл
start powershell -NoExit -Command "Set-Location -LiteralPath '%~dp0'; python replai.py --continue"