# OpenBench

OpenBench is an open-source Chess Engine Testing Framework for UCI engines. OpenBench provides a lightweight interface and client to facilitate running fixed-game tests as well as SPRT tests to benchmark changes to engines for performance and stability. OpenBench supports [Fischer Random Chess](https://en.wikipedia.org/wiki/Chess960).

OpenBench is the primary testing framework used for the development of [Ethereal.](https://github.com/AndyGrant/Ethereal) The primary instance of OpenBench can be found at [http://chess.grantnet.us](http://chess.grantnet.us/). The Primary instance of OpenBench supports development for
[Berserk](https://github.com/jhonnold/berserk), [Bit-Genie](https://github.com/Aryan1508/Bit-Genie), [BlackMarlin](https://github.com/dsekercioglu/blackmarlin), [Demolito](https://github.com/lucasart/Demolito), [Drofa](https://github.com/justNo4b/Drofa), [Ethereal](https://github.com/AndyGrant/Ethereal), [FabChess](https://github.com/fabianvdW/FabChess), [Halogen](https://github.com/KierenP/Halogen), [Igel](https://github.com/vshcherbyna/igel), [Koivisto](https://github.com/Luecx/Koivisto), [Laser](https://github.com/jeffreyan11/laser-chess-engine), [RubiChess](https://github.com/Matthies/RubiChess), [Seer](https://github.com/connormcmonigle/seer-nnue), [Stash](https://github.com/mhouppin/stash-bot), [Weiss](https://github.com/TerjeKir/weiss), [Winter](https://github.com/rosenthj/Winter), and [Zahak](https://github.com/amanjpro/zahak). A dozen or more engines are using their own private, local instances of OpenBench.

You can join OpenBench's [Discord server](https://discord.com/invite/9MVg7fBTpM) to join the discussion, see what developers are working on and talking about, or to find out how you can contribute to the project and become a part of it. OpenBench is heavily inspired by [Fishtest](https://github.com/glinscott/fishtest). The project is powered by the [Django Web Framework](https://www.djangoproject.com/) and [fastchess](https://github.com/Disservin/fastchess).

Documentation for OpenBench is available in the [Wiki](https://github.com/AndyGrant/OpenBench/wiki)

## This fork

[looak/openbench_eg](https://github.com/looak/openbench_eg) runs Elephant's tests. It is upstream, merged in as a whole (a merge commit, so upstream's history stays an ancestor and later merges work), plus a reporter that sends every test and every upload of games to [nyayo](https://github.com/looak/nyayo), a worker that names and tags each game, a worker's walk through a test reported step by step, and the smoke tests below. [docs/spec.md](./docs/spec.md) says what it adds, how it is deployed and what each part does.

After taking this code: `pip install -r requirements.txt` (the server needs `zstandard` for its migrations), `python manage.py migrate`, and workers need `make`, a C++ compiler and GitHub to build `fastchess-ob` and the engines. Engines and books are rows of the database, edited on the website under *Manage*; the lab's Elephant is made by a migration from [Engines/elephant.json](./Engines/elephant.json).

Unit tests are scripts, run from `UnitTests/`: `for t in test_*.py; do python $t; done`.

## Local isolated smoke test

To validate server/client API compatibility before redeploying, run:

```bash
python Scripts/smoke_client_server.py
```

This uses [settings_isolated.py](./OpenSite/settings_isolated.py) to create a temporary isolated SQLite database, starts a local Django server, creates an enabled test user/profile, and verifies JSON responses for:

- `clientVersionRef`
- `clientMatchRunnerVersionRef`
- `clientWorkerInfo`
- `clientGetWorkload`

It also seeds an active workload and runs a short `Client/client.py` subprocess smoke check to detect:

- client self-update loops (`Downloading newer version of Client...`)
- bad workload JSON responses (`OpenBenchBadServerResponseException`)
- client/server version contract mismatches (`Bad Client Version`)

If `make` is not on `PATH`, the subprocess phase is skipped (endpoint and workload checks still run).

## Full smoke test

On Linux or WSL, with `make`, g++ and `pip install -r requirements.txt -r Client/requirements.txt -r Scripts/smoke/requirements.txt`:

```bash
python Scripts/smoke_client_server.py --full [--nyayo PATH_TO_NYAYO --nyayo-python PYTHON_OF_NYAYO] [--only N] [--keep]
```

It plays whole tests on one machine, with fastchess and a toy engine, and checks every report sent to nyayo and every game uploaded. The first run builds `fastchess-ob` from source (a few minutes); a copy is kept in `~/.cache/openbench-smoke/`. The scenarios are in [docs/spec.md](./docs/spec.md).
