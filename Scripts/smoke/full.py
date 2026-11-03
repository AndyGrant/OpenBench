# The full smoke test: an isolated server, the real client in a temp copy of Client/,
# a test engine built with make, games played with fastchess-ob, results reported back,
# and every report the server sends to nyayo checked against Scripts/smoke/expect.py.
# Linux and WSL only. Run through Scripts/smoke_client_server.py --full.

import bz2
import collections
import hashlib
import io
import itertools
import json
import math
import os
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # OpenBench.stats, for stats checks

from smoke import expect, files
from smoke.recorders import ClientRecorder, NyayoRecorder

ROOT   = Path(__file__).resolve().parents[2]
MANAGE = ROOT / 'manage.py'

# Where the fastchess-ob a worker built is kept, so the next run doesn't build it again (delete it to)
FASTCHESS_CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'openbench-smoke' / 'fastchess-ob'

ENGINE_NAME  = 'smoke'
ENGINE_NPS   = 1000000
ENGINE_BENCH = 1000000

NYAYO_TOKEN    = 'smoke-token'
NYAYO_INSTANCE = 'smoke'

# The worker's timers, shortened in the temp copy so a scenario takes seconds, not minutes
CLIENT_TIMERS = { 'TIMEOUT_ERROR' : 1, 'TIMEOUT_WORKLOAD' : 1, 'REPORT_INTERVAL' : 2 }
CLIENT_RETRY  = 2  # Seconds a worker waits to try a test again after a verdict that isn't an engine's (the server's setting)
BENCH_LIMIT   = 3  # Seconds before a bench is over its time (Client/bench.py's 60)

# Client requests that are events in expect.py
WATCHED = { 'clientSubmitResults' : 'results', 'clientBenchError' : 'bench_error', 'clientSubmitPGN' : 'pgn',
            'clientGetWorkload' : 'workload', 'clientReportStep' : 'step' }


class SmokeFailure(Exception):
    pass


class SmokeSkip(Exception):
    pass


def preflight():
    missing = []
    if platform.system() != 'Linux':
        missing.append('Linux (run it in WSL)')
    for tool in ('make', 'g++'):
        if shutil.which(tool) is None:
            missing.append(tool)
    try:
        import chess  # noqa: F401
    except ImportError:
        missing.append('python-chess (pip install -r Scripts/smoke/requirements.txt)')
    if missing:
        raise SmokeFailure('--full needs: %s' % (', '.join(missing)))


class LogTail:

    # Copies a process's output to a file, keeping the last lines for failure reports

    def __init__(self, stream, path, keep=400):
        self.lines  = collections.deque(maxlen=keep)
        self.path   = path
        self.thread = threading.Thread(target=self.pump, args=(stream,), daemon=True)
        self.thread.start()

    def pump(self, stream):
        with open(self.path, 'w') as fout:
            for line in iter(stream.readline, ''):
                fout.write(line); fout.flush()
                self.lines.append(line.rstrip())

    def tail(self, count=60):
        return '\n'.join(list(self.lines)[-count:])


def stop_process(proc, group=False):
    if proc is None or proc.poll() is not None:
        return
    try:
        if group: os.killpg(proc.pid, signal.SIGTERM)
        else:     proc.terminate()
        proc.wait(timeout=10)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        if group: os.killpg(proc.pid, signal.SIGKILL)
        else:     proc.kill()
        proc.wait(timeout=10)


def find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class NyayoServer:

    # A real nyayo from a checkout (--nyayo PATH), its data in a temp directory, and a
    # machine token for the reporter. The nyayo recorder forwards to it. A nyayo with a
    # worker (manage.py worker: uploads taken at once, read in the background) runs it too.

    def __init__(self, checkout, python, temp):
        self.checkout = Path(checkout).resolve()
        self.python   = python
        self.data     = temp / 'nyayo'
        self.port     = find_free_port()
        self.url      = 'http://127.0.0.1:%d' % (self.port)
        self.proc     = self.log = self.worker = self.worker_log = None
        self.uploads  = (self.checkout / 'nyayo' / 'matches' / 'management' / 'commands' / 'worker.py').is_file()

        if not (self.checkout / 'manage.py').is_file() or not (self.checkout / 'nyayo').is_dir():
            raise SmokeFailure('%s is not a nyayo checkout' % (self.checkout))

        # Set explicitly, so nyayo's own .env (python-dotenv never overrides) can't point it at real data
        self.env = { k : v for k, v in os.environ.items() if not k.startswith('NYAYO_') }
        self.env.update({
            'NYAYO_DATA_DIR'      : str(self.data),
            'NYAYO_DEBUG'         : '1',
            'NYAYO_SECRET_KEY'    : 'openbench-smoke',
            'NYAYO_ALLOWED_HOSTS' : '127.0.0.1,localhost',
            'NYAYO_SEAL_AFTER'    : '2',  # A match ended and quiet this long has its open batch sealed
        })

    def manage(self, *args):
        result = subprocess.run([self.python, 'manage.py'] + list(args), cwd=self.checkout, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode:
            raise SmokeFailure('nyayo manage.py %s failed\n%s' % (args[0], result.stdout))
        return result.stdout

    def start(self):
        self.data.mkdir(parents=True)
        self.manage('migrate', '--noinput')
        self.manage('shell', '-c', (
            'from nyayo.runs.models import Machine; '
            'Machine.objects.create(name="openbench-smoke", token_hash=Machine.hash_token(%r))') % (NYAYO_TOKEN))

        self.proc = subprocess.Popen(
            [self.python, '-u', 'manage.py', 'runserver', '127.0.0.1:%d' % (self.port), '--noreload'],
            cwd=self.checkout, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.log = LogTail(self.proc.stdout, self.data.parent / 'nyayo.log')
        if self.uploads:
            self.worker = subprocess.Popen(
                [self.python, '-u', 'manage.py', 'worker', '--interval', '0.2'],
                cwd=self.checkout, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.worker_log = LogTail(self.worker.stdout, self.data.parent / 'nyayo-worker.log')

        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SmokeFailure('nyayo exited\n%s' % (self.log.tail()))
            try:
                if requests.get(self.url + '/matches', timeout=2).status_code == 200:
                    return self
            except requests.RequestException:
                pass
            time.sleep(0.25)
        raise SmokeFailure('nyayo did not start\n%s' % (self.log.tail()))

    def query(self, sql, *params):
        db = sqlite3.connect('file:%s?mode=ro' % (self.data / 'nyayo.sqlite3'), uri=True, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, params)]
        finally:
            db.close()

    def check_match(self, match_id, state, final):
        # nyayo's own record of the match agrees with OpenBench's Test row
        matches = self.query('SELECT state FROM matches_match WHERE id = ?', match_id)
        if not matches:
            return ['nyayo has no match %s' % (match_id)]
        problems = []
        if matches[0]['state'] != state:
            problems.append('nyayo has the match %s, expected %s' % (matches[0]['state'], state))
        rows = self.query('SELECT games, wins, draws, losses FROM matches_matchresult WHERE match_id = ?', match_id)
        want = { name : final[name] for name in ('games', 'wins', 'draws', 'losses') }
        if len(rows) != 1 or rows[0] != want:
            problems.append('nyayo has results %s, the Test has %s' % (rows, want))
        return problems

    def check_uploads(self, match_id, uploads):
        # nyayo kept every upload it took, the bytes as sent (their sha256) and all their games
        if self.uploads:
            return self.check_put_away(match_id, uploads)
        rows = { x['batch'] : x for x in self.query(
            'SELECT batch, games, sha256 FROM matches_gamebatch WHERE match_id = ?', match_id) }
        problems = []
        for upload in { x['upload'] : x for x in uploads }.values():
            row = rows.get(upload['upload'])
            if row is None:
                problems.append('nyayo has no upload %s' % (upload['upload']))
            elif (row['sha256'], row['games']) != (upload['sha256'], upload['games']):
                problems.append('nyayo has upload %s as %d game(s), sha256 %s; sent %d, %s' % (
                    upload['upload'], row['games'], row['sha256'][:12], upload['games'], upload['sha256'][:12]))
        extra = sorted(set(rows) - { x['upload'] for x in uploads })
        if extra:
            problems.append('nyayo has upload(s) nobody sent: %s' % (extra[:5]))
        return problems

    def check_put_away(self, match_id, uploads, timeout=30):
        # nyayo's worker read every upload and kept its games: the upload done with the sha256 sent, a card
        # per game placing both players (the subject's colour, the opponent) and the game as it came
        sent = { x['upload'] : x for x in uploads }
        pending = lambda: self.query("SELECT name FROM matches_upload WHERE match_id = ? AND state = 'pending'", match_id)
        deadline = time.time() + timeout
        while pending() and time.time() < deadline:
            if self.worker.poll() is not None:
                return ['nyayo\'s worker exited\n%s' % (self.worker_log.tail())]
            time.sleep(0.25)

        problems, rows = [], { x['name'] : x for x in self.query(
            'SELECT name, sha256, state, reason, games, appended FROM matches_upload WHERE match_id = ?', match_id) }
        for name, upload in sorted(sent.items()):
            row = rows.get(name)
            if row is None:
                problems.append('nyayo has no upload %s' % (name))
            elif row['state'] != 'done':
                problems.append('nyayo has upload %s %s: %s' % (name, row['state'], row['reason']))
            elif (row['sha256'], row['games'], row['appended']) != (upload['sha256'], upload['games'], upload['games']):
                problems.append('nyayo has upload %s as %d game(s), %d kept, sha256 %s; sent %d, %s' % (
                    name, row['games'], row['appended'], row['sha256'][:12], upload['games'], upload['sha256'][:12]))
        extra = sorted(set(rows) - set(sent))
        if extra:
            problems.append('nyayo has upload(s) nobody sent: %s' % (extra[:5]))

        # Its cards and the games as it keeps them, read through nyayo's own catalogue
        output = self.manage('shell', '-c', (
            'import json; from nyayo.matches import catalogue as c; '
            'print("SMOKE_CARDS", json.dumps([{**x, "pgn": (c.read_game(%r, x["game"]) or b"").decode()} '
            'for x in c.cards(%r)]))') % (match_id, match_id))
        cards = { x['game'] : x for x in json.loads(output.split('SMOKE_CARDS', 1)[1]) }
        games = { '%s.%d' % (name, n) : pgn for name, x in sent.items() for n, pgn in enumerate(expect.split_upload(x['data']), 1) }
        for game, pgn in sorted(games.items()):
            card = cards.get(game)
            tags = dict(re.findall(r'^\[(\w+) "([^"]*)"\]$', pgn, re.M))
            if card is None:
                problems.append('nyayo has no card for game %s' % (game))
                continue
            if card['colour'] != tags.get('Subject') or card['opponent'] is None:
                problems.append('nyayo places game %s as %s against %s, it says Subject %s' % (
                    game, card['colour'] or 'nobody', card['opponent'], tags.get('Subject')))
            if card['termination'] != tags.get('Termination', ''):
                problems.append('nyayo has game %s ended by %r, it says %r' % (game, card['termination'], tags.get('Termination')))
            if expect.normal(card['pgn']) != expect.normal(pgn):
                problems.append('nyayo keeps game %s other than it was sent' % (game))
        extra = sorted(set(cards) - set(games))
        if extra:
            problems.append('nyayo has card(s) for game(s) nobody sent: %s' % (extra[:5]))
        return problems

    def stop(self):
        stop_process(self.worker)
        stop_process(self.proc)


class Harness:

    # One server, one client, the recorders between them. With nyayo=False the server
    # gets no NYAYO_* settings, and the nyayo recorder only listens.

    def __init__(self, args, file_server, name='main', nyayo=True, nyayo_server=None):
        self.args   = args
        self.files  = file_server
        self.name   = name
        self.temp   = Path(tempfile.mkdtemp(prefix='openbench-smoke-%s-' % (name)))
        self.port   = (args.port if name == 'main' else 0) or find_free_port()
        self.url    = 'http://127.0.0.1:%d' % (self.port)
        self.nonce  = '%s %d' % (name, time.time() * 1000)
        self.server = self.client = self.session = None
        self.server_log = self.client_log = None

        self.lock       = threading.Lock()  # Orders events: recorded client requests and actions by hand
        self.expect     = expect.Expectations(NYAYO_INSTANCE)
        self.nyayo_down = False
        self.nyayo_enabled = nyayo
        self.nyayo_server = nyayo_server
        self.nyayo      = NyayoRecorder(NYAYO_TOKEN, NYAYO_INSTANCE, nyayo_server and nyayo_server.url).start()
        self.recorder   = ClientRecorder(self.url, self.on_client_event, WATCHED).start()

        self.env = os.environ.copy()
        self.env['DJANGO_SETTINGS_MODULE'] = 'OpenSite.settings_isolated'
        self.env['OPENBENCH_ISOLATED_ROOT'] = str(self.temp / 'server')
        self.env['OPENBENCH_CONFIG_DIR']    = str(self.temp / 'config')
        for key in ('NYAYO_URL', 'NYAYO_TOKEN', 'NYAYO_INSTANCE'):
            self.env.pop(key, None)
        if nyayo:
            self.env['NYAYO_URL']      = self.nyayo.url
            self.env['NYAYO_TOKEN']    = NYAYO_TOKEN
            self.env['NYAYO_INSTANCE'] = NYAYO_INSTANCE
            self.env['NYAYO_SCHEMA']   = args.schema
        self.env['OPENBENCH_STEP_RETRY_SECONDS'] = str(CLIENT_RETRY)  # A worker in trouble tries again this soon

        (self.temp / 'server').mkdir()
        self.write_config_dir()

    # Server side

    def write_config_dir(self):
        config = self.temp / 'config'
        for folder in ('Config', 'Books', 'Engines'):
            (config / folder).mkdir(parents=True)

        # Engines and books are in the database now: written as the files import_engines and import_books read
        general = json.loads((ROOT / 'Config' / 'config.json').read_text())
        (config / 'Config' / 'config.json').write_text(json.dumps(general, indent=4))

        book = { 'sha' : files.book_sha(), 'source' : self.files.add('/books/smoke.zip', files.book_zip()) }
        (config / 'Books' / ('%s.json' % files.BOOK_NAME)).write_text(json.dumps(book, indent=4))

        engine = {
            'private' : False,
            'nps'     : ENGINE_NPS,
            'source'  : self.files.url + '/engines',
            'build'   : { 'path' : '.', 'compilers' : ['g++'], 'cpuflags' : [], 'systems' : ['Linux'] },
            'test_presets' : { 'default' : {} },
        }
        (config / 'Engines' / ('%s.json' % ENGINE_NAME)).write_text(json.dumps(engine, indent=4))

    def manage(self, *args, capture=False):
        result = subprocess.run(
            [sys.executable, str(MANAGE)] + list(args), cwd=ROOT, env=self.env,
            stdout=subprocess.PIPE if capture else None, stderr=subprocess.STDOUT if capture else None,
            text=True, check=False)
        if result.returncode:
            raise SmokeFailure('manage.py %s failed\n%s' % (args[0], result.stdout or ''))
        return result.stdout

    def start_server(self):
        self.manage('migrate', '--noinput', capture=True)
        self.manage('import_books', str(self.temp / 'config' / 'Books'), capture=True)
        self.manage('import_engines', str(self.temp / 'config' / 'Engines'), capture=True)
        self.manage('shell', '-c', (
            'from django.contrib.auth.models import User; '
            'from OpenBench.models import Profile; '
            'u, _ = User.objects.get_or_create(username=%r); u.set_password(%r); u.save(); '
            'p, _ = Profile.objects.get_or_create(user=u); p.enabled = True; p.approver = True; p.save()'
        ) % (self.args.username, self.args.password), capture=True)

        self.server = subprocess.Popen(
            [sys.executable, '-u', str(MANAGE), 'runserver', '127.0.0.1:%d' % (self.port), '--noreload'],
            cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.server_log = LogTail(self.server.stdout, self.temp / 'server.log')

        payload = { 'username' : self.args.username, 'password' : self.args.password }
        self.wait_for(lambda: self.reachable('/clientVersionRef/', payload), 30, 'the server to start')
        self.login()

    def reachable(self, path, payload):
        if self.server.poll() is not None:
            raise SmokeFailure('the server exited')
        try: return requests.post(self.url + path, data=payload, timeout=2).status_code == 200
        except requests.RequestException: return False

    def login(self):
        self.session = requests.Session()
        self.session.get(self.url + '/login/', timeout=10)
        response = self.session.post(self.url + '/login/', timeout=10, allow_redirects=False, data={
            'username' : self.args.username, 'password' : self.args.password,
            'csrfmiddlewaretoken' : self.session.cookies.get('csrftoken', ''),
        })
        if 'sessionid' not in self.session.cookies:
            raise SmokeFailure('logging in failed: %d %s' % (response.status_code, response.text[:300]))

    def engine(self, label, bench=ENGINE_BENCH, broken=False, bench_mode=''):
        # Each engine gets its own sha, so the worker builds it from its own zip. A broken one doesn't compile (see
        # files.BROKEN_MAKEFILES for how); bench_mode makes its bench misbehave (engine.py)
        sha    = hashlib.sha1(('%s %s %s' % (self.nonce, label, time.time())).encode()).hexdigest()
        source = self.files.add('/engines/%s.zip' % (sha), files.engine_zip('smoke-%s' % (sha), broken, bench_mode))
        return { 'name' : label, 'source' : source, 'sha' : sha, 'bench' : bench }

    def create_test(self, dev=None, base=None, **overrides):
        dev  = dev  or self.engine('dev')
        base = base or self.engine('base')
        test = {
            'author'            : self.args.username,
            'book_name'         : files.BOOK_NAME,
            'dev_repo'          : self.files.url + '/engines',
            'dev_engine'        : ENGINE_NAME,
            'dev_options'       : 'Threads=1 Hash=16',
            'dev_time_control'  : 'N=1000',
            'base_repo'         : self.files.url + '/engines',
            'base_engine'       : ENGINE_NAME,
            'base_options'      : 'Threads=1 Hash=16',
            'base_time_control' : 'N=1000',
            'workload_size'     : 2,
            'priority'          : 1,
            'throughput'        : 100,
            'scale_nps'         : ENGINE_NPS,
            'test_mode'         : 'GAMES',
            'max_games'         : 8,
            'approved'          : True,
        }
        test.update(overrides)

        if test['test_mode'] == 'SPRT':
            test['lowerllr'] = math.log(test['beta'] / (1.0 - test['alpha']))
            test['upperllr'] = math.log((1.0 - test['beta']) / test['alpha'])

        # Made as the create page makes one: reported at once (create_workload), approved or not, and only then
        # open to workers, so no workload of it can be reported before the test is. The report is sent from the
        # shell, synchronously, since its process ends at once and a queued report would go with it.
        began, approved = time.time(), test['approved']
        output = self.manage('shell', '-c', (
            'import json; from OpenBench.models import Engine, Test; from OpenBench.nyayo import report_test; '
            'f = json.loads(%r); f.pop("approved"); '
            'dev = Engine.objects.create(**f.pop("dev")); base = Engine.objects.create(**f.pop("base")); '
            'test = Test.objects.create(dev=dev, base=base, approved=False, **f); '
            'report_test(test.id); '
            'print("SMOKE_TEST_ID", test.id)'
        ) % (json.dumps({ **test, 'dev' : dev, 'base' : base })), capture=True)

        match = re.search(r'SMOKE_TEST_ID (\d+)', output)
        if not match:
            raise SmokeFailure('creating a test printed no id\n%s' % (output))
        test_id = int(match.group(1))

        # Opened to workers only after its creation is on record, so no hand-out comes before it
        with self.lock:
            row = self.test_row(test_id)
            if self.nyayo_enabled:
                self.expect.record(began, 'create', test_id, row, row, lost=self.nyayo_down)
            if approved:
                db = sqlite3.connect(self.temp / 'server' / 'db.sqlite3', timeout=30)
                try:
                    with db:
                        db.execute('UPDATE OpenBench_test SET approved = 1 WHERE id = ?', (test_id,))
                finally:
                    db.close()
        return test_id

    def query(self, sql, *params):
        db = sqlite3.connect('file:%s?mode=ro' % (self.temp / 'server' / 'db.sqlite3'), uri=True, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, params)]
        finally:
            db.close()

    def test_row(self, test_id):
        return self.query('SELECT * FROM OpenBench_test WHERE id = ?', test_id)[0]

    def engines(self, test_id):
        test = self.test_row(test_id)
        rows = { x['id'] : x for x in self.query('SELECT * FROM OpenBench_engine WHERE id IN (?, ?)', test['dev_id'], test['base_id']) }
        return { 'dev' : rows[test['dev_id']], 'base' : rows[test['base_id']] }

    def player_names(self, test_id):
        # The worker names a game's players <engine> <branch>, as the v1 match document does
        test, engines = self.test_row(test_id), self.engines(test_id)
        return ('%s %s' % (test['dev_engine'], engines['dev']['name']), '%s %s' % (test['base_engine'], engines['base']['name']))

    def results(self, test_id):
        return self.query('SELECT * FROM OpenBench_result WHERE test_id = ?', test_id)

    # Events: what the worker said, and what the harness did by hand

    def on_workload(self, entry, forward):
        # A workload handed out: its request names no test, its answer does. One report follows
        with self.lock:
            response = forward()
            try:
                test_id = response.json()['workload']['test']['id']
            except (ValueError, KeyError, TypeError):
                return response  # No work for the machine
            if self.nyayo_enabled:
                row = self.test_row(test_id)
                self.expect.record(entry['t'], 'workload', test_id, row, row, lost=self.nyayo_down)
        return response

    def step_rows(self, test_id):
        return self.query(
            'SELECT s.step, s.side, s.state, s.at, s.tries, s.blame, s.retry_at FROM OpenBench_step s JOIN OpenBench_result r ON r.id = s.result_id '
            'WHERE r.test_id = ? ORDER BY s.id', test_id)

    def on_client_event(self, endpoint, entry, forward):
        if endpoint == 'clientGetWorkload':
            return self.on_workload(entry, forward)
        test_id = int(entry['form']['test_id'])
        with self.lock:
            before   = self.test_row(test_id)
            steps    = self.step_rows(test_id) if endpoint == 'clientReportStep' else None
            response = forward()
            after    = self.test_row(test_id)
            # A step that changes no row (a passed one reported again) is nothing to tell nyayo
            if steps is not None and steps == self.step_rows(test_id):
                return response
            if response.status_code == 200:
                event = self.expect.record(entry['t'], WATCHED[endpoint], test_id, before, after, lost=self.nyayo_down,
                                           form=entry['form'], steps=self.step_rows(test_id))
                if event.kind == 'pgn':
                    event.upload     = entry.get('files', {}).get('file', b'')
                    event.result_id  = entry['form']['result_id']
                    event.book_index = entry['form']['book_index']
                    event.lost       = self.nyayo_down  # Nothing resends an upload nyayo missed but the backfill
        return response

    def action(self, test_id, action, **fields):
        # A workload action by hand, as the test page's buttons do it
        self.settle(test_id)
        with self.lock:
            before   = self.test_row(test_id)
            response = self.session.post(
                '%s/test/%d/%s/' % (self.url, test_id, action), data=fields, allow_redirects=False, timeout=10,
                headers={ 'X-CSRFToken' : self.session.cookies.get('csrftoken', '') })
            after    = self.test_row(test_id)
            if response.status_code != 302 or 'error' in response.headers.get('Location', ''):
                raise SmokeFailure('%s on test %d: %d %s' % (action, test_id, response.status_code,
                                                             response.headers.get('Location', response.text[:200])))
            self.expect.record(time.time(), action, test_id, before, after, lost=self.nyayo_down)
        return after

    def settle(self, test_id, timeout=15):
        # Reports go through a queue on a background thread: wait until every expected one is in,
        # or one after the last event carries it (the reports between were superseded)
        want = lambda: len(self.expect.expected(test_id))
        def arrived():
            reports, expected = self.nyayo.for_test(test_id), self.expect.expected(test_id)
            return len(reports) >= len(expected) or (reports and expected[-1].t < reports[-1]['t']
                                                     and expect.matches(expected[-1], reports[-1]))
        self.wait_for(arrived, timeout, '%d report(s) for test %d' % (want(), test_id), soft=True)
        games = lambda: expect.check_games(self.events(test_id), [], [])[1]
        self.wait_for(lambda: len(self.nyayo.games_for_test(test_id)) >= games(), timeout,
                      '%d game(s) of test %d' % (games(), test_id), soft=True)
        time.sleep(0.3)

    def wait_for_uploads(self, test_id, timeout=20):
        # The worker uploads a workload's PGNs after its last results, so after the test may have ended
        uploaded = lambda: sum(len(expect.uploaded_games(x)) for x in self.events(test_id, 'pgn'))
        self.wait_for(lambda: uploaded() >= self.test_row(test_id)['games'], timeout,
                      'the worker to upload the games of test %d' % (test_id), soft=True)

    def backfill(self, *args, schema=None, games=False):
        # manage.py report_to_nyayo, recording a backfill event for each test it sends, and with
        # games=True (--games) one for each upload it sends again from the test's tar
        self.settle_all()
        with self.lock:
            ids = [x['id'] for x in self.query('SELECT id FROM OpenBench_test ORDER BY id')] if '--all' in args \
                else [int(x) for x in args]
            rows = { test_id : self.test_row(test_id) for test_id in ids }
            extra = (['--schema', schema] if schema else []) + (['--games'] if games else [])
            result = subprocess.run([sys.executable, str(MANAGE), 'report_to_nyayo'] + extra + list(map(str, args)),
                                    cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            kind = 'backfill-v1' if schema == 'v1' else 'backfill'
            for test_id in ids:
                self.expect.record(time.time(), kind, test_id, rows[test_id], self.test_row(test_id))
                for result_id, book_index, data in (self.stored_uploads(test_id) if games else []):
                    event = self.expect.record(time.time(), 'backfill-upload', test_id, rows[test_id], rows[test_id])
                    event.upload, event.result_id, event.book_index = data, result_id, book_index
                    event.old = b'[Subject "' not in bz2.decompress(data)
        if result.returncode:
            raise SmokeFailure('report_to_nyayo %s failed\n%s' % (' '.join(extra + list(map(str, args))), result.stdout[-2000:]))
        return result.stdout

    def tar_path(self, test_id):
        # Where the PGN watcher keeps a test's uploads, under the isolated server's MEDIA_ROOT
        return self.temp / 'server' / 'Media' / 'PGNs' / ('%d.pgn.tar' % (test_id))

    def stored_uploads(self, test_id):
        # The test's uploads in its tar, in order, [(result id, book index, bytes)]
        with tarfile.open(self.tar_path(test_id)) as tar:
            return [(*x.name.split('.')[1:3], tar.extractfile(x).read()) for x in tar.getmembers()]

    def settle_all(self):
        for test_id in sorted({ x.test_id for x in self.expect.events }):
            self.settle(test_id, timeout=5)

    @staticmethod
    def concerns(path, test_id):
        # A request about this test's match or its games, or about no known match at all
        match = re.match(r'^/api/matches/openbench-%s-(\d+)(/|$)' % (re.escape(NYAYO_INSTANCE)), path)
        return match is None or int(match.group(1)) == test_id

    def events(self, test_id, kind=None):
        return [x for x in self.expect.events if x.test_id == test_id and (kind is None or x.kind == kind)]

    def wait_until_released(self, test_id, timeout=30):
        # The worker learns a test ended at its next submission, which then changes nothing,
        # or it had finished the workload already and asks for the next one
        since = time.time()
        count = len(self.events(test_id))
        asked = lambda: any(x['path'].startswith('/clientGetWorkload') and x['t'] > since for x in list(self.recorder.log))
        self.wait_for(lambda: any(not x.report for x in self.events(test_id)[count:]) or asked(),
                      timeout, 'the worker to leave test %d' % (test_id))

    def verify(self, test_id):
        self.wait_for_uploads(test_id)
        self.settle(test_id)
        engines  = self.engines(test_id)
        problems = self.expect.check(
            test_id, self.nyayo.for_test(test_id), self.test_row(test_id), self.results(test_id), engines,
            resends=len(self.nyayo.unknown_for_test(test_id)))
        names    = self.player_names(test_id)
        problems += expect.check_games(self.events(test_id), self.nyayo.uploads_for_test(test_id),
                                       self.nyayo.for_test(test_id), names, self.endings(test_id))[0]
        if self.nyayo_server:
            problems += self.nyayo_server.check_uploads(
                'openbench-%s-%d' % (NYAYO_INSTANCE, test_id), self.nyayo.uploads_for_test(test_id))
        problems += expect.check_steps(self.nyayo.for_test(test_id), self.step_rows(test_id), self.results(test_id))
        problems += ['nyayo recorder: %s %s: %s' % (x['method'], x['path'], x['problem'])
                     for x in self.nyayo.violations if self.concerns(x['path'], test_id)]
        if self.nyayo_server and self.expect.expected(test_id):
            problems += self.nyayo_server.check_match('openbench-%s-%d' % (NYAYO_INSTANCE, test_id),
                                                      self.expect.state[test_id], self.test_row(test_id))
        if problems:
            raise SmokeFailure('test %d:\n  - %s\n\n%s' % (test_id, '\n  - '.join(problems), expect.timeline(
                test_id, list(self.recorder.log), self.expect.events, self.nyayo.for_test(test_id))))

    # Client side

    def endings(self, test_id):
        # the runner's Termination of each game the worker played, from its own PGNs, as { game id : tag or None }:
        # PGNs/<test>.<result>.<book index>.<time>.<copy>.pgn, the copies uploaded in order
        endings, folder = {}, self.temp / 'Client' / 'PGNs'
        files = sorted(folder.glob('%d.*.pgn' % (test_id)), key=lambda x: [int(n) for n in x.name.split('.')[:-1]])
        for (result, book), group in itertools.groupby(files, lambda x: tuple(x.name.split('.')[1:3])):
            games = re.split(r'\n\s*\n(?=\[Event )', '\n\n'.join(x.read_text().strip() for x in group))
            for number, game in enumerate(games, 1):
                found = re.search(r'^\[Termination "([^"]*)"\]', game, re.M)
                endings['%s.%s.%d' % (result, book, number)] = found and found.group(1)
        return endings

    def start_client(self):
        client = self.temp / 'Client'
        shutil.copytree(ROOT / 'Client', client, ignore=shutil.ignore_patterns(
            '__pycache__', 'PGNs', 'Engines', 'Networks', 'Books', '*.exe', 'openbench.exit'))

        worker = (client / 'worker.py').read_text()
        for name, value in CLIENT_TIMERS.items():
            worker, count = re.subn(r'^(%s\s*=\s*)\d+' % (name), r'\g<1>%d' % (value), worker, flags=re.M)
            if count != 1:
                raise SmokeFailure('worker.py has no %s to shorten' % (name))
        # The worker drains its results queue with a fixed 5 s wait, once more after every workload
        worker, count = re.subn(r'results_queue\.get\(timeout=5\)', 'results_queue.get(timeout=0.5)', worker)
        if count != 1:
            raise SmokeFailure('worker.py has no results_queue wait to shorten')
        (client / 'worker.py').write_text(worker)
        bench = (client / 'bench.py').read_text()
        bench, count = re.subn(r'^(MAX_BENCH_TIME_SECONDS\s*=\s*)\d+', r'\g<1>%d' % (BENCH_LIMIT), bench, flags=re.M)
        if count != 1:
            raise SmokeFailure('bench.py has no MAX_BENCH_TIME_SECONDS to shorten')
        (client / 'bench.py').write_text(bench)

        # fastchess-ob is built by the worker from source, minutes of compiling; a copy kept from an earlier run does
        if FASTCHESS_CACHE.is_file():
            shutil.copy2(FASTCHESS_CACHE, client / 'fastchess-ob')

        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHON'] = sys.executable  # The test engine's makefile writes this into the shebang
        env['PATH']   = os.path.dirname(sys.executable) + os.pathsep + env.get('PATH', '')

        self.client = subprocess.Popen(
            [sys.executable, '-u', str(client / 'client.py'),
             '-U', self.args.username, '-P', self.args.password, '-S', self.recorder.url,
             '-T', '1', '-N', '1', '-I', 'smoke-%s' % (self.name), '--no-client-downloads'],
            cwd=client, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        self.client_log = LogTail(self.client.stdout, self.temp / 'client.log')

    def client_engines(self):
        folder = self.temp / 'Client' / 'Engines'
        return sorted(x.name for x in folder.iterdir()) if folder.is_dir() else []

    # Shared

    def wait_for(self, predicate, timeout, what, soft=False):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.client is not None and self.client.poll() is not None:
                raise SmokeFailure('the client exited while waiting for %s' % (what))
            if predicate():
                return True
            time.sleep(0.25)
        if soft:
            return False
        raise SmokeFailure('timed out after %ds waiting for %s' % (timeout, what))

    def report_logs(self):
        for name, log in (('server', self.server_log), ('client', self.client_log)):
            if log:
                print('\n---- %s %s log (tail; full log in %s) ----\n%s' % (self.name, name, log.path, log.tail()))

    def close(self, keep):
        stop_process(self.client, group=True)
        built = self.temp / 'Client' / 'fastchess-ob'
        if built.is_file() and not FASTCHESS_CACHE.is_file():
            FASTCHESS_CACHE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built, FASTCHESS_CACHE)
        stop_process(self.server)
        self.recorder.stop()
        self.nyayo.stop()
        if keep: print('Kept %s' % (self.temp))
        else:    shutil.rmtree(self.temp, ignore_errors=True)


def check(condition, message):
    if not condition:
        raise SmokeFailure(message)


def score(row):
    return '%d games (+%d =%d -%d)' % (row['games'], row['wins'], row['draws'], row['losses'])


# Scenarios: each a fresh test on the same server and client, leaving it inactive

def scenario_games_to_max(h):
    test_id = h.create_test(test_mode='GAMES', max_games=8)
    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))

    test, results = h.test_row(test_id), h.results(test_id)
    check(test['games'] == test['max_games'], 'played %d games, max_games is %d' % (test['games'], test['max_games']))
    check(test['wins'] + test['draws'] + test['losses'] == test['games'], 'W+D+L is not the game count')
    check(test['LL'] + test['LD'] + test['DD'] + test['DW'] + test['WW'] == test['games'] // 2,
          'the pentanomial counts are not half the game count')
    check(len(results) == 1 and results[0]['games'] == test['games'], 'the Result row disagrees with the Test')
    check(len(h.client_engines()) >= 2, 'the client did not build both engines: %s' % (h.client_engines()))
    check(len(h.events(test_id, 'results')) >= 2, 'expected a report per batch, saw one batch')

    h.verify(test_id)
    return 'test %d: %s, %d reports' % (test_id, score(test), len(h.nyayo.for_test(test_id)))

def scenario_sprt_to_result(h):
    # The base plays any legal move, so the dev wins nearly every pair and the SPRT ends quickly
    test_id = h.create_test(test_mode='SPRT', elolower=0.0, eloupper=200.0, alpha=0.05, beta=0.05,
                            base_options='Threads=1 Hash=16 Strength=0')
    h.wait_for(lambda: h.test_row(test_id)['finished'], 120, 'SPRT test %d to finish' % (test_id))

    test = h.test_row(test_id)
    check(test['passed'] or test['failed'], 'the SPRT finished with neither a pass nor a fail')
    h.verify(test_id)
    return 'test %d: %s, LLR %.2f, %s' % (test_id, score(test), test['currentllr'], 'passed' if test['passed'] else 'failed')

def scenario_stop(h):
    # Approved and modified by hand first: each a report with the state unchanged
    test_id = h.create_test(test_mode='GAMES', max_games=1000, approved=False)
    h.action(test_id, 'APPROVE')
    h.action(test_id, 'MODIFY', priority=1, throughput=50, workload_size=2)
    h.wait_for(lambda: h.test_row(test_id)['games'] >= 4, 60, 'test %d to play 4 games' % (test_id))

    h.action(test_id, 'STOP')
    h.wait_until_released(test_id)
    h.verify(test_id)
    return 'test %d: stopped at %s' % (test_id, score(h.test_row(test_id)))

def scenario_delete(h):
    test_id = h.create_test(test_mode='GAMES', max_games=1000)
    h.wait_for(lambda: h.test_row(test_id)['games'] >= 4, 60, 'test %d to play 4 games' % (test_id))

    h.action(test_id, 'DELETE')
    h.wait_until_released(test_id)
    h.verify(test_id)
    return 'test %d: deleted at %s' % (test_id, score(h.test_row(test_id)))

def scenario_restore(h):
    test_id = h.create_test(test_mode='GAMES', max_games=1000)
    h.wait_for(lambda: h.test_row(test_id)['games'] >= 4, 60, 'test %d to play 4 games' % (test_id))
    h.action(test_id, 'DELETE')
    h.wait_until_released(test_id)

    games = h.action(test_id, 'RESTORE')['games']
    h.wait_for(lambda: h.test_row(test_id)['games'] > games, 60, 'restored test %d to play again' % (test_id))
    h.action(test_id, 'STOP')
    h.wait_until_released(test_id)
    h.verify(test_id)
    return 'test %d: restored at %d games, stopped at %s' % (test_id, games, score(h.test_row(test_id)))

def scenario_crash_then_stop(h):
    # The dev exits after a few moves in every game; tight error bounds keep the SPRT open
    test_id = h.create_test(test_mode='SPRT', elolower=0.0, eloupper=5.0, alpha=1e-6, beta=1e-6,
                            dev_options='Threads=1 Hash=16 CrashAfter=6')
    h.wait_for(lambda: sum(x['crashes'] for x in h.results(test_id)) > 0, 60, 'test %d to count a crash' % (test_id))

    check(not h.test_row(test_id)['finished'], 'the SPRT finished before it could be stopped')
    h.action(test_id, 'STOP')
    h.wait_until_released(test_id)
    h.verify(test_id)
    return 'test %d: %d crashes, stopped' % (test_id, sum(x['crashes'] for x in h.results(test_id)))

def scenario_nyayo_down(h):
    test_id = h.create_test(test_mode='GAMES', max_games=16)
    h.wait_for(lambda: h.nyayo.for_test(test_id), 60, 'the first report for test %d' % (test_id))

    with h.lock:
        h.nyayo_down = True
        h.nyayo.stop()
    h.wait_for(lambda: any(x.lost for x in h.events(test_id, 'results')), 60, 'a batch while nyayo is down')
    lost_at = len(h.recorder.log)
    time.sleep(1)  # Let the reporter fail on it

    with h.lock:
        h.nyayo.start()
        h.nyayo_down = False

    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
    h.verify(test_id)

    # The worker never noticed: every request it made was answered by the server
    failed = [x for x in list(h.recorder.log)[:lost_at] if x.get('status') != 200]
    check(not failed, 'the worker saw failures while nyayo was down: %s' % (failed))
    check('failed to report match for test %d' % (test_id) in '\n'.join(h.server_log.lines),
          'the server never logged the failed report')
    return 'test %d: %d batch(es) lost, then %s' % (
        test_id, sum(1 for x in h.events(test_id) if not x.report and x.lost), score(h.test_row(test_id)))

def scenario_no_nyayo(h):
    # A second server and client with no NYAYO_* settings; the recorder only listens
    other = Harness(h.args, h.files, name='upstream', nyayo=False)
    try:
        other.start_server()
        other.start_client()
        test_id = other.create_test(test_mode='GAMES', max_games=8)
        other.wait_for(lambda: other.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
        time.sleep(1)
        heard = len(other.nyayo.reports) + len(other.nyayo.violations)
        check(heard == 0, 'the recorder got %d request(s) from a server with no NYAYO_URL' % (heard))
        check(other.test_row(test_id)['games'] == 8, 'the test did not play its 8 games')
        return 'test %d on a second server: %s, no reports' % (test_id, score(other.test_row(test_id)))
    except Exception:
        other.report_logs()
        raise
    finally:
        other.close(keep=h.args.keep)


def scenario_pgns(h):
    # Made with upstream's default, FALSE: the fork uploads every test's games anyway
    test_id = h.create_test(test_mode='GAMES', max_games=8, upload_pgns='FALSE')
    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
    h.verify(test_id)

    want = expect.check_games(h.events(test_id), [], [])[1]
    check(h.test_row(test_id)['upload_pgns'] == 'COMPACT', 'upload_pgns is %r' % (h.test_row(test_id)['upload_pgns']))
    check(want == h.test_row(test_id)['games'], 'uploaded %d games, the test played %d' % (want, h.test_row(test_id)['games']))
    return 'test %d: %d batches, %d games in nyayo' % (
        test_id, len(h.events(test_id, 'pgn')), len(h.nyayo.games_for_test(test_id)))


def scenario_backfill(h):
    test_id = h.create_test(test_mode='GAMES', max_games=8)
    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
    h.verify(test_id)

    # One test, as the live report would be; then --all, one report for every test there is
    before = len(h.nyayo.reports)
    h.backfill(test_id)
    h.verify(test_id)
    check(len(h.nyayo.reports) == before + 1, 'report_to_nyayo %d sent %d reports' % (test_id, len(h.nyayo.reports) - before))

    tests  = len(h.query('SELECT id FROM OpenBench_test'))
    before = len(h.nyayo.reports)
    h.backfill('--all')
    h.settle_all()
    check(len(h.nyayo.reports) == before + tests, '--all sent %d reports for %d tests' % (len(h.nyayo.reports) - before, tests))
    h.verify(test_id)
    return 'test %d resent, then all %d tests' % (test_id, tests)


def scenario_move_to_v1(h):
    # A test reported in OpenBench's own shape, then resent as v1: nyayo moves the match once
    if not h.nyayo_server:
        raise SmokeSkip('needs --nyayo: only a real nyayo can move a match')
    if h.args.schema != 'openbench':
        raise SmokeSkip('needs --schema openbench: the live reports must be in the old shape')

    test_id = h.create_test(test_mode='SPRT', elolower=0.0, eloupper=200.0, alpha=0.05, beta=0.05,
                            base_options='Threads=1 Hash=16 Strength=0')
    h.wait_for(lambda: h.test_row(test_id)['finished'], 120, 'SPRT test %d to finish' % (test_id))
    h.verify(test_id)

    h.backfill(test_id, schema='v1')
    h.verify(test_id)

    match_id = 'openbench-%s-%d' % (NYAYO_INSTANCE, test_id)
    rows = h.nyayo_server.query('SELECT opponent FROM matches_matchresult WHERE match_id = ?', match_id)
    games = h.nyayo_server.query('SELECT DISTINCT opponent FROM matches_game WHERE match_id = ?', match_id)
    check([x['opponent'] for x in rows] == ['base'], 'nyayo has results for %s, not base' % ([x['opponent'] for x in rows]))
    check([x['opponent'] for x in games] == ['base'], 'nyayo has games against %s, not base' % ([x['opponent'] for x in games]))
    return 'test %d moved to v1' % (test_id)


def scenario_two_tests(h):
    # Two tests at once, the first's games slow to send: the second's first report doesn't wait for them.
    # The first's games are held in the recorder until the second's report arrives (each 3 s at most).
    # The second's first report is its first results, as for a test made on the website.
    dev, base = h.engine('dev'), h.engine('base')  # Shared, so the second test needs no build
    first    = h.create_test(test_mode='GAMES', max_games=1000, dev=dev, base=base)
    released = threading.Event()
    h.nyayo.hold_games(first, released, 3)

    try:
        h.wait_for(lambda: h.events(first, 'pgn'), 60, 'test %d to upload a batch of games' % (first))
        # The higher priority: the worker's next workload is the second's
        second = h.create_test(test_mode='GAMES', max_games=4, dev=dev, base=base, priority=2)
        h.wait_for(lambda: h.nyayo.for_test(second), 60, 'the first report of test %d' % (second))
    finally:
        released.set()

    h.wait_for(lambda: h.test_row(second)['finished'], 60, 'test %d to finish' % (second))
    h.action(first, 'STOP')  # Once the first's games are all in
    h.wait_until_released(first)
    problems = expect.check_status_first(first, second, h.events(first), h.nyayo.games_for_test(first),
                                         h.events(second), h.nyayo.for_test(second))
    check(not problems, '; '.join(problems))
    h.verify(first)
    h.verify(second)
    return 'tests %d and %d: %s, then stopped at %s' % (
        second, first, score(h.test_row(second)), score(h.test_row(first)))


def scenario_nyayo_busy(h):
    # nyayo answers every upload 503 (busy, Retry-After 1) twice before taking it: each is sent again, none lost
    test_id = h.create_test(test_mode='GAMES', max_games=4)
    h.nyayo.busy_games(test_id, 2)
    h.wait_for(lambda: h.test_row(test_id)['finished'], 60, 'test %d to finish' % (test_id))
    h.wait_for_uploads(test_id)
    h.settle(test_id, timeout=30)
    h.verify(test_id)

    uploads = h.nyayo.uploads_for_test(test_id)
    busied  = collections.Counter(x['upload'] for x in h.nyayo.busied if x['test_id'] == test_id)
    check(uploads and all(busied[x['upload']] == 2 for x in uploads),
          'not every upload was answered 503 twice before it was taken: %s' % (dict(busied)))
    return 'test %d: %d uploads, each sent again after two 503s' % (test_id, len(uploads))


def old_style(data):
    # An upload as a worker before client 39 made it: the runner's <engine>-dev and <engine>-base,
    # no Subject, Opponent or Termination
    games = []
    for pgn in expect.split_upload(data):
        dev_white = re.search(r'^\[Subject "white"\]$', pgn, re.M) is not None
        pgn = re.sub(r'^\[(Subject|Opponent|Termination) "[^"]*"\]\n', '', pgn, flags=re.M)
        white, black = ('smoke-dev', 'smoke-base') if dev_white else ('smoke-base', 'smoke-dev')
        pgn = re.sub(r'^\[White "[^"]*"\]$', '[White "%s"]' % (white), pgn, flags=re.M)
        pgn = re.sub(r'^\[Black "[^"]*"\]$', '[Black "%s"]' % (black), pgn, flags=re.M)
        games.append(pgn)
    return bz2.compress(''.join(x + '\n\n' for x in games).encode())  # The worker's layout

def scenario_backfill_games(h):
    # report_to_nyayo --games: a test's uploads again from its tar, and one from before client 39 in it,
    # sent renamed and tagged, the same bytes on a second backfill (nyayo's 200, not a 409)
    test_id = h.create_test(test_mode='GAMES', max_games=4)
    h.wait_for(lambda: h.test_row(test_id)['finished'], 60, 'test %d to finish' % (test_id))
    h.verify(test_id)

    live = h.events(test_id, 'pgn')
    h.wait_for(lambda: h.tar_path(test_id).exists() and len(h.stored_uploads(test_id)) >= len(live), 40,
               'the PGN watcher to move the uploads of test %d into its tar' % (test_id))
    first = live[0]
    older = old_style(first.upload)
    with tarfile.open(h.tar_path(test_id), 'a') as tar:
        info = tarfile.TarInfo('%d.%s.9999.pgn.bz2' % (test_id, first.result_id))
        info.size = len(older)
        tar.addfile(info, io.BytesIO(older))

    h.backfill(test_id, games=True)
    h.verify(test_id)
    h.backfill(test_id, games=True)
    h.verify(test_id)

    name = '%s.9999' % (first.result_id)
    sent = [x for x in h.nyayo.uploads_for_test(test_id) if x['upload'] == name]
    check(len(sent) == 2 and sent[0]['sha256'] == sent[1]['sha256'] != hashlib.sha256(older).hexdigest(),
          'the older upload was sent %d time(s), not twice with the same new bytes' % (len(sent)))
    return 'test %d: %d uploads sent again twice, one from before client 39 named and tagged (%s)' % (
        test_id, len(live), ', '.join(str(x['status']) for x in sent))

def scenario_from_the_start(h):
    # A test is on nyayo's list as waiting the moment it exists, before any worker may see it (it isn't approved yet,
    # and the worker is idle), and shows its worker once that worker is handed a workload
    test_id = h.create_test(test_mode='GAMES', max_games=4, approved=False)

    reports = h.nyayo.for_test(test_id)
    check(len(reports) == 1, 'expected the one report of its creation, nyayo had %d' % (len(reports)))
    doc, view = reports[0]['document'], expect.view(reports[0]['document'])
    check(view['state'] == 'waiting', 'the test is %r on creation, not waiting' % (view['state']))
    check(view['counts']['games'] == 0 and not view['machines'], 'a waiting test has no games and no machines: %s' % (doc))
    check(not h.results(test_id), 'a worker has the test, which is unapproved')
    if h.args.schema == 'v1':
        check(doc['match']['settings']['tc'] and doc['subject']['commit'] and doc['opponents'][0]['commit'],
              'the first document lacks the settings or the engines: %s' % (doc))
        check(doc['match']['finished_at'] is None, 'finished_at on a waiting test: %s' % (doc['match']['finished_at']))

    h.action(test_id, 'APPROVE')  # A report of its own, still waiting
    h.wait_for(lambda: any(expect.view(x['document'])['machines'] for x in h.nyayo.for_test(test_id)), 30,
               'the worker to show in a report of test %d' % (test_id))
    shown = next(x for x in h.nyayo.for_test(test_id) if expect.view(x['document'])['machines'])
    check(expect.view(shown['document'])['state'] == 'waiting' and expect.view(shown['document'])['counts']['games'] == 0,
          'the worker showed only once games were played: %s' % (shown['document']))

    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
    h.verify(test_id)
    return 'test %d: waiting on creation, its worker shown at hand-out, then %s' % (test_id, score(h.test_row(test_id)))

def scenario_named(h):
    # A test created with a name is that name on nyayo from its first report to its last, and its games still carry
    # <engine> <branch> (verify reads them); one created without is <engine> <branch> vs <branch>. A name found at
    # creation (a branch or a commit's first line for a sha) is a unit test, since the harness makes tests in the
    # database and never asks GitHub
    if h.args.schema != 'v1':
        return 'skipped: OpenBench own document has no match name'

    named   = h.create_test(test_mode='GAMES', max_games=4, name='Smoke: a name for a test')
    unnamed = h.create_test(test_mode='GAMES', max_games=4)
    for test_id, want in ((named, 'Smoke: a name for a test'), (unnamed, '%s dev vs base' % (ENGINE_NAME))):
        h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
        h.verify(test_id)
        names = { x['document']['match']['name'] for x in h.nyayo.for_test(test_id) }
        check(names == { want }, 'test %d reached nyayo as %s, expected %r' % (test_id, sorted(names), want))
    return 'test %d named, test %d by its engine and branches' % (named, unnamed)

def last_walk(h, test_id):
    # The newest report's walk of the one machine, as { (step, side) : step }
    for report in reversed(h.nyayo.for_test(test_id)):
        for machine in expect.view(report['document'])['machines']:
            if machine.get('steps'):
                return { (x['step'], x.get('side')) : x for x in machine['steps'] }
    raise SmokeFailure('no report of test %d carries a walk' % (test_id))

def scenario_walk(h):
    # A passing walk reaches nyayo step by step: picked up, both compiles, both benches, running, and only
    # then games. The worker comes round for more workloads and its steps stay passed.
    test_id = h.create_test(test_mode='GAMES', max_games=8, workload_size=1)  # A workload is 4 games here (fastchess: 2 per round, 2 rounds), so two for 8
    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'test %d to finish' % (test_id))
    h.verify(test_id)  # Also: every walk in a report, in order, never back after passing; the last as OpenBench has it

    if h.args.schema != 'v1':
        return 'test %d: not a v1 document, walks not sent' % (test_id)

    reports = h.nyayo.for_test(test_id)
    walks   = []
    for report in reports:
        doc = expect.view(report['document'])
        for machine in doc['machines']:
            if machine.get('steps'):
                walks.append((doc['state'], machine))
    check(walks, 'no report carries a walk')

    # Waiting while the walk is on, running from the step that passes running
    for state, machine in walks:
        running = next(x for x in machine['steps'] if x['step'] == 'running')['state'] == 'passed'
        check(state not in ('running', 'waiting') or (state == 'running') == running,
              'the match is %s with running %s' % (state, 'passed' if running else 'not passed'))

    first = walks[0][1]['steps']
    check(first[0]['step'] == 'picked_up' and first[0]['state'] == 'passed', 'the first walk does not start picked up: %s' % (first))

    steps = last_walk(h, test_id)
    check(all(x['state'] == 'passed' for x in steps.values()), 'the walk did not pass in full: %s' % ([x['state'] for x in steps.values()]))
    check(steps[('compile', 'dev')].get('cached') is False and steps[('compile', 'dev')].get('seconds') is not None,
          'dev compile: %s' % (steps[('compile', 'dev')]))
    for side in ('dev', 'base'):
        check(steps[('bench', side)].get('nodes') == ENGINE_BENCH and steps[('bench', side)].get('nps'),
              '%s bench: %s' % (side, steps[('bench', side)]))
    seen = { tuple(x['state'] for x in machine['steps']) for _, machine in walks }
    check(len(seen) >= 3, 'the walk was seen in %d state(s), expected it step by step' % (len(seen)))

    # Handed out more than once, counted, with no step back to pending (check_steps)
    hands = len(h.events(test_id, 'workload'))
    count = walks[-1][1].get('workloads')
    check(hands >= 2 and count == hands, '%d workload(s) handed out, nyayo was told %s' % (hands, count))
    return 'test %d: %d reports, %d with a walk in %d states, %d workloads, all steps passed' % (
        test_id, len(reports), len(walks), len(seen), hands)

# Bounds an SPRT of the toy engine doesn't reach, so it stays open until it is stopped
SPRT_OPEN = { 'test_mode' : 'SPRT', 'elolower' : 0.0, 'eloupper' : 5.0, 'alpha' : 1e-6, 'beta' : 1e-6 }

def verdict_of(h, test_id):
    # The newest report's match.verdict, or None
    reports = h.nyayo.for_test(test_id)
    return (reports[-1]['document'].get('match') or {}).get('verdict') if reports else None

def newest(h, test_id):
    return (h.nyayo.for_test(test_id) or [{ 'document' : { 'match' : {} } }])[-1]['document']['match']

def step_row(h, test_id, step, side):
    rows = [x for x in h.step_rows(test_id) if (x['step'], x['side']) == (step, side)]
    return rows[0] if rows else None

def failed_start(h):
    return h.args.schema == 'v1' and h.nyayo_enabled

def scenario_worker_trouble(h, dev, base, what):
    # A failure that is the machine's: the test goes on, waiting, and the worker is handed it again, after the
    # time the server gave, and keeps count. Only a person ends it here.
    test_id = h.create_test(dev=dev, base=base, **SPRT_OPEN)
    side    = what['side']
    # Its second failure, judged once both engines have been through the stage
    h.wait_for(lambda: (step_row(h, test_id, what['step'], side) or {}).get('tries', 0) >= 2 and step_row(h, test_id, what['step'], side)['blame'], 60,
               'the worker to try test %d twice' % (test_id))
    row = step_row(h, test_id, what['step'], side)
    check(row['blame'] == 'worker', 'the verdict is %r, expected worker; steps %s' % (row['blame'], [(x['step'], x['side'], x['state'], x['tries'], x['blame']) for x in h.step_rows(test_id)]))
    check(not h.test_row(test_id)['finished'], 'a worker\'s failure stopped the test')
    check(len(h.events(test_id, 'workload')) >= 2, 'the worker was not handed the test again')
    check(h.test_row(test_id)['games'] == 0, 'games were played')

    if failed_start(h):
        h.settle(test_id)
        match = newest(h, test_id)
        check(match['state'] == 'waiting' and match['finished_at'] is None, 'the match is %r, finished_at %r' % (match['state'], match['finished_at']))
        check((match.get('verdict') or {}).get('blame') == 'worker', 'verdict %s' % (match.get('verdict')))
        walk = last_walk(h, test_id)[(what['step'], side)]
        check(walk['state'] in ('failed', 'active', 'pending') and walk.get('tries', 0) >= 2, 'the step %s' % (walk))
        failed = [x for x in newest_walks(h, test_id) if x['state'] == 'failed']
        check(not failed or all(x.get('blame') == 'worker' and x.get('retry_at') and 'tries again' in x.get('effect', '') for x in failed),
              'a failed step lacks its verdict: %s' % (failed))

    if h.args.linger:
        return 'test %d: left open to look at' % (test_id)

    h.action(test_id, 'STOP')
    h.wait_until_released(test_id)
    h.verify(test_id)
    return 'test %d: a worker\'s failure (%s), %d tries, the test went on' % (test_id, what['why'], row['tries'])

def newest_walks(h, test_id):
    # The steps of the newest report that carries any
    for report in reversed(h.nyayo.for_test(test_id)):
        for machine in expect.view(report['document'])['machines']:
            if machine.get('steps'):
                return machine['steps']
    return []

def scenario_machine_log(h):
    return scenario_worker_trouble(h, h.engine('dev', broken='space'), h.engine('base'),
                                   { 'step' : 'compile', 'side' : 'dev', 'why' : 'the log says no disk space' })

def scenario_both_fail_to_compile(h):
    return scenario_worker_trouble(h, h.engine('dev', broken='source'), h.engine('base', broken='source'),
                                   { 'step' : 'compile', 'side' : 'dev', 'why' : 'both engines fail to compile' })

def scenario_bench_slow_on_both(h):
    return scenario_worker_trouble(h, h.engine('dev', bench_mode='slow'), h.engine('base', bench_mode='slow'),
                                   { 'step' : 'bench', 'side' : 'dev', 'why' : 'both benches over their time' })

def scenario_bench_fails_to_run_on_both(h):
    return scenario_worker_trouble(h, h.engine('dev', bench_mode='silent'), h.engine('base', bench_mode='silent'),
                                   { 'step' : 'bench', 'side' : 'dev', 'why' : 'neither bench ran' })

def scenario_engine_verdict(h, dev, step, summary, why):
    # The engine's failure: the other engine passed beside it, the worker is told to stop, and the test is a failed start
    test_id = h.create_test(dev=dev, **SPRT_OPEN)
    h.wait_for(lambda: h.test_row(test_id)['finished'], 60, 'the verdict to stop test %d' % (test_id))
    row = step_row(h, test_id, step, 'dev')
    check(row['blame'] == 'engine', 'the verdict is %r, expected engine' % (row['blame']))
    check(not h.query('SELECT id FROM OpenBench_logevent WHERE test_id = ? AND machine_id = 0 AND summary = "STOP"', test_id),
          'a stop by hand')
    check(h.query('SELECT id FROM OpenBench_logevent WHERE test_id = ? AND summary LIKE "Stopped: %"', test_id),
          'no event for the verdict that stopped the test')
    check(step_row(h, test_id, step, 'base')['state'] == 'passed', 'base %s beside the failed dev' % (step_row(h, test_id, step, 'base')['state']))
    check(h.test_row(test_id)['games'] == 0, 'games were played')
    asked = len(h.events(test_id, 'workload'))
    time.sleep(3)
    check(len(h.events(test_id, 'workload')) == asked == 1, 'the worker was handed the test %d time(s)' % (asked))
    h.verify(test_id)

    if failed_start(h):
        match = newest(h, test_id)
        check(match['state'] == 'failed_prechecks' and match['finished_at'], 'the match is %r, finished_at %r' % (match['state'], match['finished_at']))
        verdict = match.get('verdict') or {}
        check(verdict.get('blame') == 'engine' and verdict.get('summary') == summary and verdict.get('seen_on') == ['smoke-main'],
              'verdict %s' % (verdict))
        walk = last_walk(h, test_id)[(step, 'dev')]
        check(walk['state'] == 'failed' and walk['blame'] == 'engine' and walk['effect'].startswith('The test stops.')
              and walk['evidence'] and all(x['points_at'] == 'engine' or x['points_at'] == 'either' for x in walk['evidence']),
              'the failed step: %s' % (walk))
        return test_id, verdict
    return test_id, None

def scenario_compile_fails(h):
    # Dev doesn't compile. The worker builds base all the same, the control, then stops there. Base compiled, and the
    # error has a file and a line: the engine's. The test is stopped by the verdict, not by hand.
    test_id, verdict = scenario_engine_verdict(h, h.engine('dev', broken='source'), 'compile', "Dev doesn't compile", 'compile')
    if verdict:
        check(verdict['where'] == 'src/eval/mobility.cpp:212', 'where: %s' % (verdict['where']))
        steps = last_walk(h, test_id)
        check(steps[('compile', 'dev')].get('tries') == 1 and 'mobility.cpp:212' in steps[('compile', 'dev')]['log'],
              'dev compile: %s' % (steps[('compile', 'dev')]))
        check(all(steps[key]['state'] == 'pending' for key in (('bench', 'dev'), ('bench', 'base'), ('running', None))),
              'a step past the failed compile was reached: %s' % ([x['state'] for x in steps.values()]))
        states = [expect.view(x['document'])['state'] for x in h.nyayo.for_test(test_id)]
        check(states[-1] == 'failed_prechecks' and set(states[:-1]) == { 'waiting' }, 'the match went %s' % (states))
    return 'test %d: dev failed to compile, base compiled beside it, the verdict stopped the test' % (test_id)

def scenario_bench_mismatch(h):
    # A wrong bench on dev, and base matched on the same machine, with no other worker to have matched: the engine's
    test_id, verdict = scenario_engine_verdict(h, h.engine('dev', bench=ENGINE_BENCH + 1), 'bench',
                                               "Dev's bench doesn't match its commit", 'bench')
    check(h.events(test_id, 'bench_error'), 'no bench error was reported')
    if verdict:
        steps = last_walk(h, test_id)
        check(steps[('bench', 'dev')]['detail'] == 'Wrong bench: %d, expected %d' % (ENGINE_BENCH, ENGINE_BENCH + 1),
              'the failed bench says %r' % (steps[('bench', 'dev')]['detail']))
        check(steps[('bench', 'base')].get('nodes') == ENGINE_BENCH and steps[('bench', 'base')].get('nps'),
              'base bench has no nodes and speed: %s' % (steps[('bench', 'base')]))
        check(steps[('running', None)]['state'] == 'pending', 'running is %s after a failed bench' % (steps[('running', None)]['state']))
    return 'test %d: wrong bench on dev, base matched, the verdict stopped the test' % (test_id)

def scenario_bench_slow(h):
    test_id, _ = scenario_engine_verdict(h, h.engine('dev', bench_mode='slow'), 'bench', "Dev's bench runs over 60 seconds", 'bench')
    return 'test %d: dev over its bench time, base within it, the verdict stopped the test' % (test_id)

def scenario_bench_fails_to_run(h):
    test_id, _ = scenario_engine_verdict(h, h.engine('dev', bench_mode='silent'), 'bench', 'Dev failed to run its bench', 'bench')
    return 'test %d: dev\'s bench ran nothing, base\'s did, the verdict stopped the test' % (test_id)

def scenario_wrong_on_both(h):
    # Both engines' benches are wrong on the one machine: nothing says whose. One more try, then the worker leaves
    # and, with no one else to play it, the test is held
    return scenario_unclear(h, h.engine('dev', bench=ENGINE_BENCH + 1), h.engine('base', bench=ENGINE_BENCH + 1),
                            'bench', "Dev's bench doesn't match its commit, and no other worker has tried it")

def scenario_killed(h):
    # The compiler is killed: not a compile error. Nobody else has tried it, so nobody can tell. One more try, then held.
    # Restarted by hand, every walk starts over and the worker is handed it again
    return scenario_unclear(h, h.engine('dev', broken='killed'), h.engine('base'), 'compile',
                            "Dev's compile was killed, and no other worker has tried it", restart=True)

def scenario_unclear(h, dev, base, step, summary, restart=False):
    test_id = h.create_test(dev=dev, base=base, **SPRT_OPEN)
    held    = lambda: (step_row(h, test_id, step, 'dev') or {}).get('tries', 0) >= 2 and step_row(h, test_id, step, 'dev')['blame']
    h.wait_for(held, 60, 'the worker to try test %d twice' % (test_id))
    row = step_row(h, test_id, step, 'dev')
    check(row['blame'] == 'unclear', 'the verdict is %r, expected unclear' % (row['blame']))
    check(not h.test_row(test_id)['finished'], 'a failure nobody can place stopped the test')
    check(not row['retry_at'], 'the worker was given a third try')

    # It has left the test: not handed it again, however long it asks
    hands = len(h.events(test_id, 'workload'))
    time.sleep(CLIENT_RETRY + 3)
    check(len(h.events(test_id, 'workload')) == hands == 2, 'handed out %d time(s), then %d' % (hands, len(h.events(test_id, 'workload'))))

    if failed_start(h):
        h.settle(test_id)
        match = newest(h, test_id)
        check(match['state'] == 'held' and match['finished_at'] is None, 'the match is %r, finished_at %r' % (match['state'], match['finished_at']))
        verdict = match.get('verdict') or {}
        check(verdict.get('blame') == 'unclear' and verdict.get('summary') == summary, 'verdict %s' % (verdict))
        walk = last_walk(h, test_id)[(step, 'dev')]
        check(walk['blame'] == 'unclear' and walk['tries'] == 2 and walk['effect'].startswith('The test is held'), 'the step %s' % (walk))

    if restart:
        # Restarted by hand, as the page offers it on a held test: every walk starts over, tries too, and the hold goes
        h.action(test_id, 'RESTART')
        row = step_row(h, test_id, step, 'dev')
        check((row['state'], row['tries'], row['blame']) == ('pending', 0, ''), 'after a restart: %s' % (row))
        h.wait_for(held, 60, 'the worker to try test %d twice again' % (test_id))
        check(len(h.events(test_id, 'workload')) == 4, 'handed out %d time(s) after a restart' % (len(h.events(test_id, 'workload'))))
        if failed_start(h):
            h.settle(test_id)
            check(newest(h, test_id)['state'] == 'held', 'the match is %r again' % (newest(h, test_id)['state']))

    if h.args.linger:
        return 'test %d: left open to look at' % (test_id)

    h.action(test_id, 'STOP')
    h.wait_until_released(test_id)
    h.verify(test_id)
    return 'test %d: nobody could place it, one more try, held%s' % (test_id, ', restarted by hand and held again' if restart else '')

def scenario_later_workload(h):
    # A bench right on the first workload and wrong on a later one: the same binary gave two answers, which is the
    # engine's, whoever else has matched. The test has games, so it is an error, not a failed start.
    test_id = h.create_test(workload_size=1, dev=h.engine('dev', bench_mode='flip'), **SPRT_OPEN)
    h.wait_for(lambda: h.test_row(test_id)['finished'], 90, 'the verdict to stop test %d' % (test_id))
    row = step_row(h, test_id, 'bench', 'dev')
    check(row['blame'] == 'engine' and h.test_row(test_id)['games'] > 0, 'verdict %r with %d games' % (row['blame'], h.test_row(test_id)['games']))
    h.verify(test_id)

    if failed_start(h):
        match = newest(h, test_id)
        check(match['state'] == 'error' and match['finished_at'], 'the match is %r, finished_at %r' % (match['state'], match['finished_at']))
        check((match.get('verdict') or {}).get('blame') == 'engine', 'verdict %s' % (match.get('verdict')))
        walk = last_walk(h, test_id)[('bench', 'dev')]
        check('two answers' in walk['evidence'][0]['text'] and 'games kept' in walk['effect'], 'the step %s' % (walk))
    return 'test %d: bench right, then wrong on a later workload, %d games kept, error' % (test_id, h.test_row(test_id)['games'])


SCENARIOS = collections.OrderedDict([
    ('1',  ('GAMES test to max_games',          scenario_games_to_max)),
    ('2',  ('SPRT with wide bounds to a result', scenario_sprt_to_result)),
    ('3',  ('stop mid-test',                     scenario_stop)),
    ('4',  ('delete mid-test, not stopped',      scenario_delete)),
    ('5',  ('restore after a delete',            scenario_restore)),
    ('6',  ('wrong bench on dev, base matched: the engine\'s', scenario_bench_mismatch)),
    ('7',  ('engine crashes, then stopped',      scenario_crash_then_stop)),
    ('8',  ('nyayo down for a while',            scenario_nyayo_down)),
    ('9',  ('no NYAYO_URL',                      scenario_no_nyayo)),
    ('10', ('every game reaches nyayo',          scenario_pgns)),
    ('11', ('report_to_nyayo TEST_ID and --all',  scenario_backfill)),
    ('12', ('a match moves to v1',                scenario_move_to_v1)),
    ('13', ('two tests, status ahead of games',   scenario_two_tests)),
    ('14', ('nyayo busy for games (503)',         scenario_nyayo_busy)),
    ('15', ('report_to_nyayo --games, an older upload', scenario_backfill_games)),
    ('16', ('reported from creation, waiting; its worker at hand-out', scenario_from_the_start)),
    ('17', ('a passing walk, step by step',     scenario_walk)),
    ('18', ('dev fails to compile; base compiled beside it: the engine\'s', scenario_compile_fails)),
    ('19', ('a test with a name is that on nyayo',  scenario_named)),
    ('20', ('the log says no disk space: the worker\'s', scenario_machine_log)),
    ('21', ('both engines fail to compile: the worker\'s', scenario_both_fail_to_compile)),
    ('22', ('compiler killed, nobody else has tried: held, then restarted', scenario_killed)),
    ('23', ('wrong bench on both engines: held', scenario_wrong_on_both)),
    ('24', ('both benches over their time: the worker\'s', scenario_bench_slow_on_both)),
    ('25', ('dev\'s bench over its time, base\'s not: the engine\'s', scenario_bench_slow)),
    ('26', ('dev\'s bench fails to run, base\'s runs: the engine\'s', scenario_bench_fails_to_run)),
    ('27', ('neither bench runs: the worker\'s', scenario_bench_fails_to_run_on_both)),
    ('28', ('a bench right, then wrong on a later workload: the engine\'s', scenario_later_workload)),
])

# Not written yet, each waiting on the work named
PENDING = {
}


def run_scenario(harness, key):
    title, run = SCENARIOS[key]
    xfail, began = expect.xfail(key, harness.args), time.time()
    try:
        detail = run(harness)
    except SmokeSkip as reason:
        print('SKIP  %-3s %s (%s)' % (key, title, reason))
        return True
    except SmokeFailure as error:
        took = time.time() - began
        if xfail:
            print('XFAIL %-3s %s (%.1fs): %s\n      %s' % (key, title, took, xfail, str(error).split('\n')[0]))
            if harness.args.verbose: print(error)
            return True
        print('FAIL  %-3s %s (%.1fs): %s' % (key, title, took, error))
        return False
    except Exception:
        print('FAIL  %-3s %s (%.1fs)' % (key, title, time.time() - began))
        traceback.print_exc()
        return False

    if xfail:
        print('XPASS %-3s %s (%.1fs): passes now, remove its mark in expect.py (%s)' % (key, title, time.time() - began, xfail))
        return False
    print('PASS  %-3s %s (%.1fs) %s' % (key, title, time.time() - began, detail or ''))
    return True


def main(args):
    preflight()

    selected = args.only.split(',') if args.only else list(SCENARIOS) + list(PENDING)
    unknown  = [x for x in selected if x not in SCENARIOS and x not in PENDING]
    if unknown:
        raise SmokeFailure('unknown scenario(s): %s' % (', '.join(unknown)))

    started, failed, nyayo = time.time(), [], None
    with files.FileServer() as file_server:
        harness = Harness(args, file_server)
        try:
            if args.nyayo:
                nyayo = NyayoServer(args.nyayo, args.nyayo_python or sys.executable, harness.temp).start()
                harness.nyayo.target, harness.nyayo_server = nyayo.url, nyayo
            harness.start_server()
            harness.start_client()

            for key in selected:
                if key in PENDING:
                    print('SKIP  %-3s %s (waits on %s)' % (key, *PENDING[key]))
                elif not run_scenario(harness, key):
                    failed.append(key)

            if failed:
                harness.report_logs()

            if args.linger:
                print('LINGER %ds: OpenBench at %s, nyayo at %s' % (args.linger, harness.url, nyayo and nyayo.url), flush=True)
                time.sleep(args.linger)

        except Exception:
            harness.report_logs()
            raise

        finally:
            if nyayo:
                if failed: print('\n---- nyayo log (tail; full log in %s) ----\n%s' % (nyayo.log.path, nyayo.log.tail()))
                if failed and nyayo.worker_log:
                    print('\n---- nyayo worker log (tail; full log in %s) ----\n%s' % (nyayo.worker_log.path, nyayo.worker_log.tail()))
                nyayo.stop()
            harness.close(keep=args.keep or bool(failed))

    print('\nSMOKE FULL %s in %.1fs' % ('FAIL (%s)' % (', '.join(failed)) if failed else 'PASS', time.time() - started))
    return 1 if failed else 0
