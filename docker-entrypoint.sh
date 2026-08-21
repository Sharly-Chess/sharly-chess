#!/bin/sh
# On a brand-new data volume, Sharly Chess asks interactively whether to
# install example event databases (dev-mode only, see
# src/common/data_recovery.py). There is no non-interactive flag for it, so
# answer "n" via stdin; `exec` keeps this process as PID 1 so signals
# (docker stop) still reach it directly for a graceful shutdown.
exec python src/sharly_chess.py --path /data "$@" <<'EOF'
n
EOF
