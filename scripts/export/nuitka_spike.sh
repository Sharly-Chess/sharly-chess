#!/usr/bin/env bash
# Nuitka spike build — kill-switch test: does the compiled toga app launch?
# Args (hidden imports + data files) are generated from the SAME collection logic
# as the PyInstaller builder, via nuitka_args.py — so the two bundles stay in parity.
# Run from BASE_DIR (repo root). NOT a production builder — just proves feasibility.
set -euo pipefail

PY=./venv/bin/python
OUT=dist-nuitka
export VIRTUAL_ENV="$PWD/venv"

rm -rf "$OUT" 2>/dev/null || true
rm -rf "$OUT" 2>/dev/null || true

# Generate the parity arg list (one flag per line).
"$PY" scripts/export/nuitka_args.py > /tmp/nuitka_args.txt

# Read generated flags into an array (portable; macOS ships bash 3.2, no mapfile).
GEN_ARGS=()
while IFS= read -r line; do
  [ -n "$line" ] && GEN_ARGS+=("$line")
done < /tmp/nuitka_args.txt

"$PY" -m nuitka \
  --mode=app \
  --output-dir="$OUT" \
  --output-filename=sharly-chess \
  --assume-yes-for-downloads \
  --no-deployment-flag=self-execution \
  --macos-app-name=sharly-chess \
  --macos-app-icon=src/web/static/images/sharly-chess.icns \
  --macos-signed-app-name=com.sharly-chess.app \
  "${GEN_ARGS[@]}" \
  src/sharly_chess.py
