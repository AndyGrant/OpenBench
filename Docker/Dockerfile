FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

# Install basic compilers + tools
# bash: required by entrypoint.sh and the worker's login shell
# build-essential: gcc/g++/make + glibc headers for C/C++ sources
# libclang-dev: provides libclang.so, needed by rust-bindgen (e.g. Reckless/Fathom)
# libclang-rt-dev: provides libclang_rt.profile.a for clang PGO (-fprofile-instr-generate)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates make cmake wget curl git python3 python3-pip \
    build-essential pkg-config libssl-dev \
    clang libclang-dev libclang-rt-dev llvm lld gdb valgrind \
    && rm -rf /var/lib/apt/lists/*

# Engine builds invoke versioned tool names (e.g. llvm-profdata-22). Ubuntu
# normally ships these, but add symlinks for any that are missing.
RUN V=$(clang -dumpversion | cut -d. -f1) && \
    for tool in llvm-profdata llvm-cov clang clang++; do \
        if [ ! -e "/usr/bin/${tool}-${V}" ] && [ ! -e "/usr/local/bin/${tool}-${V}" ]; then \
            ln -s "$(command -v ${tool})" "/usr/local/bin/${tool}-${V}"; \
        fi; \
    done

# Tools needed by OpenBench + Torch
RUN pip3 install --break-system-packages py-cpuinfo psutil requests certifi charset-normalizer idna numpy urllib3 zstandard

# ---------- Global Rust install ----------

ENV CARGO_HOME=/usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup
ENV PATH=/usr/local/cargo/bin:$PATH

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --no-modify-path && \
    rustup component add llvm-tools && \
    cargo install cargo-pgo && \
    chmod -R a+w $CARGO_HOME $RUSTUP_HOME

# target-cpu=native must be set here: engine Makefiles set it via
# `RUSTFLAGS ?=`, which defers to this ENV. Set after `cargo install` above
# so cargo-pgo itself stays portable across worker CPUs.
ENV RUSTFLAGS="-C target-cpu=native"

# ----------------------------------------

# Setup the OpenBench worker's file structures
RUN useradd -m -s /bin/bash worker && \
    mkdir -p /home/worker/workdir && \
    chown -R worker:worker /home/worker

USER worker

# client.py bootstraps the rest of the OpenBench client (worker.py and its
# deps) from the server at runtime, so that's all we need to fetch here.
RUN mkdir -p /home/worker/OpenBench/Client && \
    curl -fsSL https://raw.githubusercontent.com/AndyGrant/OpenBench/master/Client/client.py \
        -o /home/worker/OpenBench/Client/client.py

# credentials.<engine> files are bind-mounted read-only into the Client dir
# at `docker run` time (see manage.py --creds), never baked into the image.

WORKDIR /home/worker/workdir

COPY entrypoint.sh /home/worker/workdir/entrypoint.sh

# All fields below are supplied per-container at `docker run` time
# (see manage.py), so a single image can back all worker instances.
ENV OB_USER="" \
    OB_PASS="" \
    OB_SERVER="" \
    OB_IDENTITY="" \
    OB_THREADS=""

ENTRYPOINT [ "/home/worker/workdir/entrypoint.sh" ]
