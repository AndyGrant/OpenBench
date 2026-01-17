#!/usr/bin/env bash

if [ -z "$OPENBENCH_USERNAME" ];
then
    echo "Username is not set. Please set the OPENBENCH_USERNAME variable."
    exit 1
fi

if [ -z "$OPENBENCH_PASSWORD" ];
then
    echo "Password is not set. Please set the OPENBENCH_PASSWORD variable."
    exit 1
fi

if [ -z "$OPENBENCH_SERVER" ];
then
    echo "Server is not set. Please set the OPENBENCH_SERVER variable."
    exit 1
fi

SOCKETS=$(lscpu | awk -F: '/^Socket\(s\):/ { gsub(/ /,"",$2); print $2; exit }')

if [ -z "$SOCKETS" ];
then
    echo "Error: could not detect Socket(s) from lscpu" >&2
    exit 1
fi

# This formula is ideal for selecting the correct number of threads for high number of cores, leaving enough leeway for
# Cutechess to not be subjected to time-losses.
# However, it may not be optimal for low core counts - would love to hear feedback on possible adjustments
THREADS=$(
    awk -v N="$(nproc)" -v S="$SOCKETS" 'BEGIN {
        t = N - int(0.75 * sqrt(N))
        printf "%d", t - (t % S)
    }'
)

exec python client.py \
    --username "$OPENBENCH_USERNAME" \
    --password "$OPENBENCH_PASSWORD" \
    --threads "$THREADS" \
    --nsockets "$SOCKETS" \
    --server "$OPENBENCH_SERVER" \
    -I "$(hostname)"