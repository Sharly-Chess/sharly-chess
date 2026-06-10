# Nuitka spike build (Windows) — kill-switch test: does the compiled toga app launch?
# Mirror of nuitka_spike.sh. Args (hidden imports + data files) come from the SAME
# nuitka_args.py the PyInstaller builder logic feeds, so the bundles stay in parity.
# Run from the repo root in PowerShell:
#     powershell -ExecutionPolicy Bypass -File scripts\export\nuitka_spike_win.ps1
# NOT a production builder (no signing) — just proves feasibility. UNTESTED on Windows
# (authored on macOS); expect to iterate on a missing dynamic-import tree or two.
$ErrorActionPreference = 'Stop'

$Py  = '.\venv\Scripts\python.exe'
$Out = 'dist-nuitka'
$env:VIRTUAL_ENV = (Resolve-Path '.\venv').Path

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }

# Generate the parity arg list (one flag per line), then read it into an array.
$argsFile = Join-Path $env:TEMP 'nuitka_args.txt'
& $Py scripts\export\nuitka_args.py | Out-File -Encoding utf8 $argsFile
$genArgs = Get-Content $argsFile | Where-Object { $_ -ne '' }

& $Py -m nuitka `
  --mode=standalone `
  --output-dir=$Out `
  --output-filename=sharly-chess `
  --assume-yes-for-downloads `
  --windows-icon-from-ico=src/web/static/images/sharly-chess.ico `
  --windows-console-mode=attach `
  @genArgs `
  src/sharly_chess.py

# Result: dist-nuitka\sharly_chess.dist\sharly-chess.exe
# Launch:  .\dist-nuitka\sharly_chess.dist\sharly-chess.exe
# For a production GUI (no console window) switch --windows-console-mode=attach to =disable.
