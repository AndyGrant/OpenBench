#!/bin/bash
set -euo pipefail

trap 'touch openbench.exit' SIGTERM SIGINT

: "${OB_USER:?OB_USER must be set}"
: "${OB_PASS:?OB_PASS must be set}"
: "${OB_SERVER:?OB_SERVER must be set}"
: "${OB_IDENTITY:?OB_IDENTITY must be set}"
: "${OB_THREADS:?OB_THREADS must be set}"

# credentials/ is bind-mounted read-only (see manage.py --creds) and may hold
# one credentials.<engine> file per engine; symlink them alongside client.py
# so OpenBench can find whichever one it needs for the engine under test.
shopt -s nullglob
for f in /home/worker/credentials/credentials.*; do
    ln -sf "$f" "/home/worker/OpenBench/Client/$(basename "$f")"
done

python3 -u /home/worker/OpenBench/Client/client.py \
    -U "${OB_USER}" \
    -P "${OB_PASS}" \
    -S "${OB_SERVER}" \
    -T "${OB_THREADS}" \
    -N 1 \
    -I "${OB_IDENTITY}"
