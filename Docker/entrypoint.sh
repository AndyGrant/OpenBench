#!/bin/bash
set -euo pipefail

trap 'touch openbench.exit' SIGTERM SIGINT

: "${OPENBENCH_USERNAME:?OPENBENCH_USERNAME must be set}"
: "${OPENBENCH_PASSWORD:?OPENBENCH_PASSWORD must be set}"
: "${OPENBENCH_SERVER:?OPENBENCH_SERVER must be set}"
: "${OPENBENCH_IDENTITY:?OPENBENCH_IDENTITY must be set}"
: "${OPENBENCH_THREADS:?OPENBENCH_THREADS must be set}"

# credentials/ is bind-mounted read-only (see manage.py --creds) and may hold
# one credentials.<engine> file per engine; symlink them alongside client.py
# so OpenBench can find whichever one it needs for the engine under test.
shopt -s nullglob
for f in /home/worker/credentials/credentials.*; do
    ln -sf "$f" "/home/worker/OpenBench/Client/$(basename "$f")"
done

python3 -u /home/worker/OpenBench/Client/client.py \
    -U "${OPENBENCH_USERNAME}" \
    -P "${OPENBENCH_PASSWORD}" \
    -S "${OPENBENCH_SERVER}" \
    -T "${OPENBENCH_THREADS}" \
    -N 1 \
    -I "${OPENBENCH_IDENTITY}"
