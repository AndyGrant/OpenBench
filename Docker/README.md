# OpenBench Docker Workers

Run one or more OpenBench workers in Docker, each pinned to its own set of CPU
cores (and NUMA node where possible). The image is based on Ubuntu 26.04.
Everything is driven through the `Makefile`, which wraps `manage.py`.

All commands below are run from this `Docker/` directory. Docker and `python3`
must be available on the host, and your user must be allowed to talk to the
Docker daemon (e.g. in the `docker` group).

## Commands

| Command                                                        | Description                                                                           |
|----------------------------------------------------------------|---------------------------------------------------------------------------------------|
| `make plan THREADS=<n> COUNT=<n>`                              | Preview how the machine's cores would be split across workers. Starts nothing.        |
| `make spawn THREADS=<n> COUNT=<n> PREFIX=<name> [CREDS=<dir>]` | Build the image, then start `COUNT` pinned workers of `THREADS` logical threads each. |
| `make list`                                                    | Show the status of all worker containers.                                             |
| `make enter WORKER=<label>`                                    | Open a bash shell in a running worker, e.g. `WORKER=A`.                               |
| `make kill`                                                    | Force-remove **all** worker containers from the image.                                |
| `make build`                                                   | Build the image without spawning anything.                                            |

## Getting started

### 1. Run `make plan` first

```
make plan THREADS=<n> COUNT=<n>
```

- `THREADS`: logical threads per worker, **including SMT siblings**. It must be a
  multiple of the machine's SMT width (2 on most x86 CPUs).
- `COUNT`: number of workers.

`plan` reads the CPU topology from `/sys` and prints which CPUs and NUMA memory
nodes each worker would get:

```
$ make plan THREADS=8 COUNT=4
detected 64 logical threads, 2-way SMT
  worker A: cpus 0-3,32-35  mems 0
  ...
```

It fails if the request doesn't fit, i.e. `THREADS * COUNT` exceeds the logical
threads or the physical cores available. Each worker's client is given
`THREADS - 1` threads for search; one thread is left for the container and OS.

### 2. Set your credentials

`make spawn` reads three environment variables, the same ones the `Scripts/`
tools use, and refuses to run without them:

| Variable             | Meaning                                          |
|----------------------|--------------------------------------------------|
| `OPENBENCH_USERNAME` | Your OpenBench username                          |
| `OPENBENCH_PASSWORD` | Your OpenBench password                          |
| `OPENBENCH_SERVER`   | Server URL, e.g. `https://openbench.example.com` |

Export them in your shell, or keep them in a local, uncommitted file and source it:

```
# .env
export OPENBENCH_USERNAME=myname
export OPENBENCH_PASSWORD=mypassword
export OPENBENCH_SERVER=https://openbench.example.com
```

```
source .env
```

`OPENBENCH_IDENTITY` and `OPENBENCH_THREADS` are set per container by
`manage.py`, so you don't set them yourself.

### 3. Spawn workers

```
make spawn THREADS=<n> COUNT=<n> PREFIX=<name> [CREDS=<dir>]
```

This starts `COUNT` detached containers named `openbench-client-A`, `-B`, and so
on, each pinned with `--cpuset-cpus` and `--cpuset-mems`.

- `PREFIX`: the worker identity prefix shown on the server, so `PREFIX=gpu101`
  gives `gpu101-A`, `gpu101-B`, and so on. Use something unique per host.
- `CREDS` (optional): a directory of `credentials.<engine>` files. It is
  bind-mounted read-only into the container and linked next to `client.py`. The
  files are never baked into the image.

Full example:

```
source .env
make plan  THREADS=32 COUNT=8
make spawn THREADS=32 COUNT=8 PREFIX=gpu101 CREDS=$HOME/ob-credentials
make list
```

## Notes

- Logs for a worker: `docker logs -f openbench-client-A`.
- To change the layout or pick up a new image, run `make kill` and then
  `make spawn` again. `kill` removes every worker on the machine, not just one.

## Troubleshooting

- `error: environment variable OPENBENCH_USERNAME must be set`: source your
  `.env` in the same shell you run `make` from.
- `--threads must be a multiple of N`: your CPU has N-way SMT; use a multiple of N.
- `exceeds ... logical threads` or `need ... physical cores`: reduce `THREADS`
  or `COUNT`. Check with `make plan` first.
- `--creds directory not found`: `CREDS` must point to an existing directory.
- A container name is already in use: run `make kill` first.
