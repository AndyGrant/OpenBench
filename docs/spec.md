# OpenBench integration

Upstream: [AndyGrant/OpenBench](https://github.com/AndyGrant/OpenBench), not maintained here · this fork:
[looak/openbench_eg](https://github.com/looak/openbench_eg) · instance on bobby :8000, worker hunt

## Purpose

OpenBench is where Elephant's strength is measured: SPRT tests of a branch against a base, played by workers. This
spec covers what Elephant has to provide for that to work, how the owner uses it, and what the fork adds to upstream:
reporting every test and every game to nyayo, and the smoke test that proves it.

## Scope

**Here:** the build OpenBench expects, the bench contract, engine configuration on the instance, the testing workflow,
the fork's additions and how it's deployed, and how other components read OpenBench.

**Not here:** upstream's code and its statistics (see its docs), worker internals, the match document's fields (nyayo's
[`docs/match-schema.md`](https://github.com/looak/nyayo/blob/main/docs/match-schema.md) owns them, *OpenBench* and
*Batches* in particular), where the work is going (ramani's `openbench.md`, *Direction*).

## Current

### What Elephant provides

- **A makefile build.** OpenBench builds `ob_build/makefile` with `make EXE=<name>` and g++. The binary's entry is
  `src/cli/src/openbench.cpp`; `ARCH` defaults to `native`.
- **`<binary> bench`** on the command line prints `<nodes> nodes <nps> nps` as its last line. The node count must
  equal the `bench <nodes> nodes` line in the newest commit of the tested branch, or OpenBench flags the test. The
  commit hook writes that line from the same makefile build ([Elephant's spec, *Bench*](https://github.com/looak/elephant/blob/main/docs/spec/engine.md#bench)).
- **UCI** with `Threads`, `Hash` and `Move Overhead`.

### The instance

- bobby (172.16.100.11) runs the fork under Django `runserver` on :8000 as `openbench.service`: the checkout
  `~/dev/openbench_eg` on `master`, the conda env `py-ob` (Python 3.10), started by `run.sh` (bobby's own, untracked,
  with the auto-reloader on, so a checkout restarts it). The owner edits server files and runs `sudo` there.
- **Deploying**: `deploy/update.sh` pulls the current branch, installs `requirements.txt`, migrates, collects static
  files and restarts the service. `deploy/env.sh` finds the Python: `OPENBENCH_BIN`, `OPENBENCH_CONDA_ENV`, the active
  conda env, or an env named `openbench`, in that order.
- **Settings for nyayo** come from `/etc/openbench/nyayo.env` (root only), read by the unit's drop-in
  (`openbench.service.d/override.conf`, `EnvironmentFile=`): see *Reporting to nyayo*.
- hunt (172.16.100.15, 32 cores) is the worker. It plays with cutechess-ob, and downloads the client from the fork's
  `master` (`client_repo_url` and `client_repo_ref` in `Config/config.json`) when the server asks for a newer one.
  The server's client version, in `Config/config.json`, and the worker's, `CLIENT_VERSION` in `Client/worker.py`, are
  both **40**. A change to the client that hunt must take raises both.

### Engine configuration

Elephant's configuration is the fork's `Engines/elephant.json`: built from `ob_build`, reference nps **1198000**
(unchanged since it was added, 2025-12-10). OpenBench scales time controls by that reference against what a worker
measures with `bench`. The reference must be recalibrated whenever the bench changes, or test TCs come out wrong; a
stale value once stretched 8+0.08 to roughly 42+0.42. The bench uses one 16 MB TT for all positions since 1.0.0 so it
isn't dominated by page faults when a worker benches many copies at once: about 4.4M nps alone, 2.85M per copy at 16
copies (1.0.0).

Elephant is the only engine the create page offers (`Config/config.json`, `engines`): every test here is Elephant
against Elephant, and gauntlets against other engines are played by uwanja. The other engines' `Engines/*.json` files
stay so upstream merges stay clean; one is offered again by listing it. `Engines/elephant.json` defaults a test's book
to `8moves_v3.epd` (`book_name`).

### Testing workflow

- **One change per branch**, SPRT'd against a fixed base for the cycle (e.g. 0.15.2 for the herd cycle), at 8+0.08.
- **Bounds** in normalized Elo: `[0, 5]` for a gain, `[-3, 1]` non-regression for fixes and refactors. Multi threaded
  changes test 4 threads against 4 (`Hash 32`).
- **Cap** around 4000–5000 games; still near LLR 0 by then, the branch is parked (kept on GitHub, notes on why).
- Winners merge into the cycle branch; a combined SPRT of the cycle against the previous release goes in the release
  notes.
- Changes that are node-identical (same bench) can merge on smoke & extended alone, the owner's call (1.0.2).
- **Every test uploads its games.** `Upload PGNs` is `COMPACT` or `VERBOSE`, never `FALSE`: the create page doesn't
  offer it, creation turns it into `COMPACT`, and an older test is switched when it next hands out a workload. Both
  keep cutechess's whole comment per move (score, depth/seldepth, time, nodes); `VERBOSE` adds `GameEndTime`.
- **A game leaves the worker named and tagged** (client 39 on). The worker rewrites each game's tags in
  `Client/pgn_util.py` (`pgn_strip_headers`, called by `compress_list_of_pgns`), as the match document names the sides:

  | Tag | Upload |
  |:--|:--|
  | `White`, `Black` | `<engine> <branch>`, from cutechess's `<engine>-dev` and `<engine>-base`; a `"` in a name becomes `'` |
  | `Subject` | `white` or `black`: the colour dev played |
  | `Opponent` | `base` |
  | `Termination` | kept (cutechess writes it only when a game isn't ended by the rules: adjudication, a time loss, a crash) |

  The other tags and the move text are upstream's stripping, unchanged. cutechess still plays under
  `name=<engine>-dev` and `name=<engine>-base`: `Cutechess.update_results` reads its `Finished game` lines by word
  position, and a name with a space would break the counts. Uploads from before client 39 keep `-dev` and `-base`, no
  `Subject`, and no `Termination`.

### What the fork adds

Upstream, plus:

| Part | Where |
|:--|:--|
| the reporter: every test, and every upload of games, to nyayo | `OpenBench/nyayo.py`, started from `apps.py`; queued from `workloads/create_workload.py`, `workloads/get_workload.py`, `utils.update_test`, `views.client_bench_error`, `views.client_report_step`, `views.client_submit_pgn` and `workloads/modify_workload.py` |
| `manage.py report_to_nyayo [--all \| TEST_ID ...] [--schema openbench\|v1] [--games]` | `OpenBench/management/commands/` |
| every test uploads its PGNs | `utils.always_upload`, `workloads/create_workload.py`, `workloads/get_workload.py`, the create page |
| the worker names and tags each game, and keeps `Termination` | `Client/pgn_util.py`, `Client/worker.py` |
| `OPENBENCH_CONFIG_DIR`, where `Config/`, `Books/` and `Engines/` are read from (the repo root by default) | `OpenSite/settings.py`, `OpenBench/config.py` |
| uploads kept under `MEDIA_ROOT/PGNs`, not a path relative to the working directory | `OpenBench/pgn_watcher.py`, `OpenBench/views.py` |
| migrations `0002`–`0006` for databases older than the models (missing columns added when absent; `0006` declares the legacy `Result` counters); `0007` adds `Step` and `Result.workloads` | `OpenBench/migrations/` |
| the client: compiling with at most 4 threads (a low spec machine), and a workload's PGN file named by its book index too, so two workloads starting in the same second don't share one | `Client/utils.py`, `Client/worker.py` |
| `Scripts/archive2nps.py` takes the side from `Subject` when a game has one | `Scripts/archive2nps.py` |
| the deploy scripts | `deploy/` |
| a worker's walk through a test, reported as it goes, and the verdict on a failed step (*Reporting to nyayo*) | `OpenBench/steps.py`, `OpenBench/models.py` (`Step`, `Result.workloads`), `views.client_report_step`, `workloads/get_workload.py`, `workloads/modify_workload.py`, `Client/worker.py` |
| a failed start shown on OpenBench's own pages | `testResultColour` and `startProblem` in `OpenBench/templatetags/mytags.py`, `Templates/OpenBench/workload.html`, `statblock-start` in `OpenBench/static/style.css` |
| the full smoke test | `Scripts/smoke_client_server.py`, `Scripts/smoke/` |
| unit tests | `UnitTests/` (`test_pgn_util.py`, `test_game_names.py`, `test_steps.py`, `test_verdict.py`, `test_client_retry.py`: scripts, run from `UnitTests/`) |

### Reporting to nyayo

The reporter is off unless `NYAYO_URL`, `NYAYO_TOKEN` and `NYAYO_INSTANCE` are set. Its documents are nyayo's contract
([`docs/match-schema.md`](https://github.com/looak/nyayo/blob/main/docs/match-schema.md), *OpenBench* and *Batches*);
this section says when OpenBench sends what.

| Setting | On bobby | Means |
|:--|:--|:--|
| `NYAYO_URL` | nyayo on :8001 | where reports and uploads go |
| `NYAYO_TOKEN` | the machine token from nyayo's admin | `Authorization: Bearer` |
| `NYAYO_INSTANCE` | `openbench` | ids are `openbench-<instance>-<test id>`; changing it makes every test a new match |
| `NYAYO_SCHEMA` | `v1` (also the default) | `v1`, nyayo's match schema, or `openbench`, the reporter's older shape, which nyayo refuses (`400`) from nyayo `0913a6c` on; kept for the smoke test's move of an old match |
| `NYAYO_OPENBENCH_URL` | `http://172.16.100.11:8000` | makes the link back to a test (`producer.url`) absolute |

Not nyayo's, but the verdict's: `OPENBENCH_STEP_RETRY_SECONDS` (`STEP_RETRY_SECONDS`, 300) is how long a worker in trouble is told to wait before it tries a test again; the smoke test makes it 2.

- **When**: one match document when a test is created (on commit, whatever its approval, so before any worker has seen
  it), when a workload is handed out (once it's committed: the machine is now on the test), when a step of a worker's
  walk changes (`clientReportStep`, only if it changed a row), after every batch of
  results (once the batch is in both the `Test` and its `Result` row), every bench error and every action by hand
  (approve, stop, delete, restore, modify). Each upload of games follows its workload's last results. The first
  document holds every field nyayo fixes for a match (the settings, the engines, the SPRT's bounds), and a test can't
  change any of them, so no later document differs (nyayo answers `409` to a difference). From `waiting` on, nyayo
  must be at or after `6f951d6`, which refuses a state it doesn't know: don't deploy this before it.
- **When a test ended** (`finished_at` of a match that isn't running): a test that passes, fails or runs out of games
  ends inside OpenBench's `update_test` with no event, so it ends at its newest result (later results are refused); a
  test stopped or deleted by hand at its newest `STOP` or `DELETE` event; a bench error at the worker's event. Never
  at the newest event of any kind, which can be the test's `CREATE` or a worker's crash in the middle of the run.
- **How**: two queues, each drained by its own background thread, so a slow or absent nyayo never slows a worker and a
  test's status never waits for games:

  | Queue | Holds | Thread |
  |:--|:--|:--|
  | reports | test ids, each once: a test queued again while its report still waits keeps its place, and the document is built when it is sent, so the newest state goes | `nyayo-report-loop` |
  | games | each workload's upload (`enqueue_pgn`), in the order they were made | `nyayo-game-loop` |

  A failure is logged and not retried: what was sent while nyayo was down is lost until it's sent again. The one
  retry is a `503` (nyayo busy with games) on an upload, sent again after its `Retry-After` (at most 30 s each time)
  for up to 300 s of waiting, on the games' thread only. Reports never get a `503`.
- **The state**, derived from the test every time, in this order: deleted is `stopped`, whether or not it was stopped
  or had passed first; finished with a pass or a fail is `finished` (and, for an SPRT, `sprt.result`); finished
  otherwise is `failed_prechecks` when a verdict blamed the engine for a failed step and no game was played, `error`
  when one did and games were played, else `stopped`; anything else is `held` when a failure nobody can place has left
  no worker able to play the test (games or none: a test with games and nothing playing is held too), `waiting` until a worker has passed the `running` step of its walk (or a game has
  been played, which a test from before the steps did without reporting one), and `running` from then on. An engine
  verdict is a failed `Step` row with `blame` `engine`, which a restart by hand clears. Crashes are in the counts;
  `test.error` doesn't decide the state. A test an older OpenBench stopped as `error` on a bench error is `stopped`
  when it is sent again.
- **The document** (v1): the engine as the subject, with dev's branch and sha, and `repo` from the test's `dev_repo`;
  one opponent `base`, with base's branch and `base_repo`; one row of counts with the pentanomial; for an SPRT its
  bounds, the LLR and OpenBench's own Elo and error as `stats`, computed as the test page shows them. The match's name
  is `<engine> <dev branch> vs <base branch>`. Crashes and time losses are counted under the subject, since OpenBench
  doesn't know the side. A machine is in `machines` once it has a `Result` row, which `get_workload` makes when it
  hands the test out; `active` says it is on this test now (its workload is the test and it was heard from in the
  last 5 minutes); `workloads` is how many workloads of the test it has been handed, and `steps` its walk (below).
  `match.verdict` (below) is sent when the state comes from a failure. `finished_at` is set on every state that has
  ended (`finished`, `stopped`, `error`, `failed_prechecks`), not on `waiting`, `held` or `running`: nyayo expires a
  `failed_prechecks` match 48 hours after it. The older `openbench` shape has no `waiting`, `held` or `failed_prechecks`:
  it says `running`, `running` and `error`.
- **The walk** (client 40 on): each machine's walk through a test, as nyayo's *Steps*, in this order: `picked_up`,
  `compile` of `dev` and of `base`, `bench` of each, `running`. A step is a `Step` row per `Result`, not a field of it:
  `ended_at` dates a finished test by `Result.updated`, which a step arriving late must not move.
  - `get_workload` passes `picked_up` itself (no client change) and counts the workload. The worker calls
    `clientReportStep` (`test_id`, `step`, `side`, `state`, and `seconds`, `cached`, `detail`, `log`, `nodes`, `nps` when
    it has them) as each step starts (`active`) and ends (`passed` or `failed`, with the compiler's output); `running`
    is reported `passed` just before cutechess starts. It is best effort on both sides: the worker catches everything but
    a bad version, the server answers `{}` whatever it made of the report, and a lost step never fails a workload. A
    step reports to nyayo on the reports queue (a quick one may share its report with the next), only if it changed
    its row.
  - A worker that comes back keeps the steps it has passed: reporting a step passed again, or active, changes nothing,
    so its walk doesn't go back to pending at every workload. A step it fails turns failed (`tries` counts them,
    `detail` is one line, `log` the end of the compiler's output, sent as its last 4096 bytes in whole characters,
    which is all nyayo takes). Two things start it again, and differ: **a retry** (the worker was told to try again,
    and is handed the test) turns the steps that failed to pending and keeps their `tries`, which count until the
    step passes; **a restart by hand** (`RESTART`, which `modify_workload` answers with `steps.restart_walks`) turns
    every step of every worker to pending, `tries` and verdicts too, and releases a hold. A step with no row is
    `pending`; a `Result` from before the steps has no `steps`. Trouble fetching things (the zip, the book) leaves the
    compile `active` with the reason as its `detail`. A private engine's missing artifact is not judged (the step
    fails with `Artifact ... missing`, no verdict), and goes on as before.
  - The worker takes **both engines through each stage**: `complete_workload` builds dev and base, then
    `determine_scale_factor` benches both, each catching a failure so the other still runs and raising it (dev's first)
    once both are done. A stage costs at most one more compile or bench, and the other engine's result is in the
    walk. What follows a failed stage isn't reached.
- **The verdict** (`steps.settle`, on the server so a rule changes without a client version): when a stage (the two
  compiles, or the two benches) has ended on both engines of a worker, each failed step in it that has no verdict gets
  one, from the first row that fits of the plan's table (ramani `plans/sprt-steps.md`, *Whose failure it is*), by
  the step's `log` and `detail`, the other engine on the same worker, and the same step of this engine on the other
  workers. It fills `blame` (`engine`, `worker` or `unclear`), `evidence` (each with `points_at`), `effect` and
  `retry_at`, written out for a person. A compile is judged by the wording of its log (`steps.compile_kind`: the
  machine, a file and a line, killed, anything else); a bench by its `detail` (`bench_kind`: over its time, wrong,
  non-deterministic, failed to execute). A bench that passed on an earlier workload of the worker and fails with a
  wrong bench now is the engine's: the same binary gave two answers. Not built: the plan's last row, no heartbeat for
  5 minutes as a worker verdict; nyayo already shows a worker as gone quiet from `active` and its last report, and
  the test simply goes on.
  - **engine**: the test is stopped (`finished`, with a `Stopped: ...` event that dates it); with no game played its
    state is `failed_prechecks`, which nyayo expires, with games `error`. The step report is answered `{ "stop": true }`.
  - **worker**: the test goes on, the state unchanged. The worker is answered `{ "retry_after": <seconds> }`
    (`STEP_RETRY_SECONDS`, 300), `retry_at` says when, and every failure of the step counts in `tries`.
  - **unclear**: a failure nothing places. The first one gets the same retry; on the second the worker leaves the test
    (`get_workload` leaves out the tests a machine has a step failed `unclear` on with two `tries`, until a restart by
    hand). When no other worker is on the test (its workload is the test, heard from in the last 5 minutes, as nyayo's
    `active`) without a failed step, it is **held**: `held`, still open, nobody is
    told to stop, and nyayo does not expire it. Another worker's result settles it by the same table: the first
    worker's step is judged again when another worker fails the same way (engine: the test stops) or passes the step
    (worker: it may try again).
  - The worker keeps the answer (`config.answer`) and, when the workload fails on a compile or a bench, leaves the
    test in `config.blacklist` for `retry_after` seconds (5 minutes where it hears neither), dropping the entry when
    it is due, in place of never. `clientBenchError` and `clientSubmitError` still log their events (the events page and
    its logs); `clientBenchError` no longer stops the test.
- **match.verdict**, when the state comes from a failure: `failed_prechecks` or `error`: the engine's step, with
  `where` (the file and line of a compile error) and `seen_on` (the machines that failed it); `held`: the step nobody
  could place; `waiting`: every machine that took the test is in trouble of its own, `blame` `worker`. OpenBench's own
  list colours a stopped test with an engine's failure `statblock-start`, and the test page says `Failed start` or
  `Held` with the reason, and a held test shows the Restart button (it is not finished): restarting it starts every walk over and
  releases the hold. The `effect` of a step that left the test is written again at each report, since whether another
  worker can still play it changes.
- **Games**: each upload is sent whole, as one `PUT /api/matches/<id>/pgns/<result id>.<book index>`,
  `application/x-bzip2`: the bytes the worker uploaded, the same bytes `Media/PGNs/<test>.pgn.tar` keeps. nyayo reads
  nothing in the request and puts the games away in the background, so a bad upload is refused later by its worker
  (visible in nyayo's admin), not in the answer. Its games are `<result id>.<book index>.<n>`, from 1 in file order.
  - `202` taken, `200` the same bytes again, `201` from a nyayo that stored the batch in the request (before its
    worker); all three are success. `409` other bytes under the name, `400` and the rest are logged as refused.
  - `404`, nyayo doesn't know the match (it was down for its reports): the match is sent first, then the upload again.
  - An upload with a game that has no `[Subject]` (made before client 39) is renamed and tagged first, in the worker's
    layout, with `rename_players`, `subject_colour` and `tag_game`, and compressed again. Its bytes are then not the
    tar's, so their sha256 differs from the tar member's, but they are the same on every send (nyayo answers `200`,
    not `409`, to a second backfill). An upload from client 39 on goes unchanged.
- **Resending**: `report_to_nyayo` sends tests now, the way the reporter does; `--schema v1` moved every match nyayo
  had stored in the older shape to v1 (run on bobby 2026-10-17). `--games` also sends every upload of each test again,
  after its match, from the test's tar (and any upload the PGN watcher hasn't moved into it yet): the backfill of
  tests finished before the uploads were forwarded.

### The smoke test

`Scripts/smoke_client_server.py` without options is the quick check: an isolated server and the worker API by hand,
on Windows too. With `--full` (Linux or WSL, needs `make`, g++ and `Scripts/smoke/requirements.txt`, plus
`Client/requirements.txt` for the client) it runs whole tests on one machine in under two minutes:

- an isolated server (database, media and config in a temp directory, through `OPENBENCH_CONFIG_DIR`) and the real
  client from a temp copy of `Client/`, its timers shortened in the copy only;
- a toy UCI engine (`Scripts/smoke/engine/`, Python and python-chess behind a makefile) and a fixed book, served as
  zips by a local file server, so the client builds, benches and plays node-limited games with cutechess-ob;
- two recorders: one between the client and the server, one in nyayo's place. The nyayo recorder takes a match
  document (`201`, then `200`) and an upload (`202`, `200` for the same bytes, `409` for other bytes, `404` before the
  match), and can be told to hold a test's uploads (`hold_games`) or answer them `503` (`busy_games`). It can forward
  to a real nyayo (`--nyayo PATH`, `--nyayo-python`), which is then checked against its own record;
- with a nyayo that has a worker (`manage.py worker`), the harness runs it beside the server and waits until no upload
  of the match is pending. A nyayo from before the worker is checked by its `GameBatch` rows;
- `Scripts/smoke/expect.py`: what each event should send to nyayo, checked for nothing missing, nothing extra, counts
  equal to the `Test` and never going down. A report may be missing when a later event came before it arrived
  (coalesced), and an extra one is allowed for each upload nyayo answered `404`. Each upload must reach nyayo once,
  byte for byte as the worker uploaded it, its games named `<engine> <branch>` by their `Subject`, with `Opponent`
  `base` and `Termination` as cutechess wrote it (read from the worker's own `PGNs/`); an upload from before client 39
  must come renamed and tagged but for that. With a nyayo that has a worker: every upload `done` with the sha256 sent,
  and a card per game with the subject's colour, an opponent, the `Termination` and the game as sent.
- Each walk in a report is checked (`expect.check_steps`): the six steps in order, a time on every step that has begun,
  a detail on every failure, a log of at most 4096 bytes, no step back to pending or active after it passed unless one
  failed in between or the test was restarted by hand (every step but `picked_up` pending), and the last report's
  steps equal to the `Step` rows. A step is an event of its own (`step`) when
  it changed a row (or made a verdict); it leaves the state as it was, `waiting` until the worker passes `running`, so
  its report may be one with the next event's, except where it makes a verdict: the engine's stops the test
  (`failed_prechecks`, or `error` with games), and a second can't-tell on the only worker holds it (`held`). A restart
  by hand (`RESTART`) is `waiting`.
- The rig's engine fails the way a scenario asks (`files.BROKEN_MAKEFILES`: a file and a line, no disk space, killed;
  `BENCH_MODE` in `engine.py`: a bench over its time, one that prints nothing, one right once and wrong after), with
  the server's retry shortened to 2 s and the client's bench limit to 3 s in the copy. It can't stage what needs a
  second worker or a bench copy that disagrees (the rig runs one thread): a compile another worker passed, a failure
  another worker had the same way, a bench another worker matched, a non-deterministic bench; those rows are unit
  tests (`UnitTests/test_verdict.py`). `--linger SECONDS` keeps the servers up after the run, a worker's trouble and a
  hold left open, to look at nyayo's pages.
- A test is made as the create page makes it: reported (from the harness, as `create_workload` does), then opened to
  workers. A workload handed out is an event of its own (`workload`), a report with the worker in `machines`. Every
  report of a test must agree with its first on what nyayo fixes (`expect.fixed_part`, nyayo's `ingest.fixed_part`).

`--schema openbench|v1` picks the document (`v1` by default), `--only`, `--keep` and `--verbose` select and keep.
Scenarios:

| # | Scenario |
|:--|:--|
| 1 | a games test to `max_games` |
| 2 | an SPRT with wide bounds to a result |
| 3 | stop mid-test |
| 4 | delete mid-test, not stopped |
| 5 | restore after a delete |
| 6 | dev's bench is wrong and base's matched: the engine's; the verdict stops the test (`failed_prechecks`), with the walk's `Wrong bench: <got>, expected <bench>`, base's nodes and `running` not reached |
| 7 | crashes, then a stop |
| 8 | nyayo down for a while |
| 9 | no `NYAYO_URL`: a second server that sends nothing |
| 10 | a test made with `Upload PGNs` `FALSE`: every game reaches nyayo anyway |
| 11 | `report_to_nyayo` for one test and `--all` |
| 12 | a match moves to v1 (`--nyayo` and `--schema openbench`, against a nyayo from before `0913a6c`; skipped otherwise) |
| 13 | two tests at once: the second's first report arrives while the first's uploads are held back |
| 14 | nyayo busy: every upload answered `503` twice, then taken |
| 15 | `report_to_nyayo --games`, with an upload from before client 39 in the tar, twice |
| 16 | a test made and not yet approved is on nyayo as `waiting` with no games and no machines; once approved, its worker shows in a `waiting` report before any game |
| 17 | a passing walk reaches nyayo step by step (at least three different walks seen), `waiting` until `running` has passed, with the dev compile's time and both benches' nodes and speed; two workloads are counted and no step goes back |
| 18 | dev doesn't compile with a file and a line, and base's compiled beside it: the engine's; the test is stopped by the verdict, `failed_prechecks` with `finished_at` and the verdict's `where` and `seen_on`, the worker not handed it again |
| 19 | the compiler's log says no disk space: the worker's; the test goes on `waiting` and the worker is handed it again after the retry, two tries, a worker verdict in the document; stopped by hand |
| 20 | both engines fail to compile with a file and a line: the worker's |
| 21 | the compiler is killed and no other worker has tried: one more try, then the worker leaves and the test is `held` (open, no `finished_at`); restarted by hand (the page offers Restart on a held test), every walk starts over (tries 0), the worker is handed it again and it is held again |
| 22 | a wrong bench on both engines: held, as 21 |
| 23 | both benches over their time: the worker's, as 19 |
| 24 | dev's bench over its time and base's not: the engine's, as 18 |
| 25 | dev's bench prints nothing (failed to execute) and base's runs: the engine's |
| 26 | neither bench runs: the worker's |
| 27 | a bench right on the first workload and wrong on a later one: the engine's, with games played, so `error` and not a failed start |

A scenario marked expected-to-fail in `expect.py` makes the run fail once it passes. None is marked.

### Who reads OpenBench

| Reader | How |
|:--|:--|
| nyayo | pushed to: every test and every upload of games, above |

## Interfaces

| Direction | What | Contract |
|:--|:--|:--|
| Elephant → OpenBench | makefile, `bench` output, commit message bench line, UCI options | above |
| OpenBench → people | test pages, SPRT results | OpenBench's |
| OpenBench → nyayo | a match document per test, and each upload of games, whole | nyayo's [`docs/match-schema.md`](https://github.com/looak/nyayo/blob/main/docs/match-schema.md): match schema v1 (*OpenBench*), and the batch endpoint (*Batches*), the contract for the uploads' tags |
