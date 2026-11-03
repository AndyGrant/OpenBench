import bz2
import collections
import datetime
import logging
import os
import queue
import re
import tarfile
import threading

import requests
from django.conf import settings
from django.utils import timezone

import OpenBench.stats

from OpenBench.models import LogEvent, PGN, Result, Test

logger = logging.getLogger(__name__)


class LatestQueue:

    # The tests whose match is waiting to be sent, each once and in the order first queued. A test
    # queued again while it waits keeps its place: its document is built when it's sent, so the
    # report sent is the newest anyway.

    def __init__(self):
        self.order   = collections.deque()
        self.waiting = set()
        self.ready   = threading.Condition()

    def put(self, test_id):
        with self.ready:
            if test_id not in self.waiting:
                self.waiting.add(test_id)
                self.order.append(test_id)
                self.ready.notify()

    def get(self, timeout):
        with self.ready:
            if not self.order and not self.ready.wait_for(lambda: self.order, timeout):
                raise queue.Empty
            test_id = self.order.popleft()
            self.waiting.discard(test_id)
            return test_id


# Match reports and games each have their own queue and thread, so a test's status never waits
# behind games, its own or another test's (ramani plans/live-updates.md, Status apart from games)
REPORT_QUEUE = LatestQueue()
GAME_QUEUE   = queue.Queue()
REPORT_STOP  = threading.Event()
REPORT_THREAD = GAME_THREAD = None

# How long a game is sent again while nyayo answers 503 (busy), before it's given up and logged
GAME_BUSY_LIMIT = 300


def nyayo_enabled():
    return bool(
        getattr(settings, 'NYAYO_URL', '').strip()
        and getattr(settings, 'NYAYO_TOKEN', '').strip()
        and getattr(settings, 'NYAYO_INSTANCE', '').strip()
    )


def build_match_id(test):
    instance = getattr(settings, 'NYAYO_INSTANCE', 'local')
    return 'openbench-%s-%s' % (instance, test.id)


def stopped_by_bench_error(test):
    # The test's newest bench error is newer than its newest action by hand (a restart, say).
    # Only client_bench_error logs a worker's event without a log file; a worker's other
    # errors (crashes, illegal moves) come with one, and may arrive after a stop by hand.
    events   = LogEvent.objects.filter(test_id=test.id)
    bench    = events.exclude(machine_id=0).filter(log_file='').order_by('-id').first()
    by_hand  = events.filter(machine_id=0).order_by('-id').first()
    return bench is not None and (by_hand is None or bench.id > by_hand.id)


def match_state(test):
    # (state, sprt.result), derived from the test every time (openbench-reports.md, The fixes). A test no
    # worker has played a game of is waiting (ramani plans/sprt-steps.md); the steps will tell it from running
    if test.deleted:
        return 'stopped', None
    if test.finished and (test.passed or test.failed):
        if test.test_mode != 'SPRT':
            return 'finished', None
        return 'finished', 'passed' if test.passed else 'failed'
    if test.finished:
        return ('error' if stopped_by_bench_error(test) else 'stopped'), None
    if not Result.objects.filter(test=test, games__gt=0).exists():
        return 'waiting', None
    return 'running', None


def schema_in_use(schema=None):
    schema = schema or getattr(settings, 'NYAYO_SCHEMA', '') or 'v1'
    if schema not in ('openbench', 'v1'):
        raise ValueError('NYAYO_SCHEMA must be openbench or v1, not %r' % (schema))
    return schema


def build_match_document(test, schema=None):
    if schema_in_use(schema) == 'v1':
        return build_v1_document(test)
    return build_openbench_document(test)


def ended_at(test, state, rows):
    # When a test that isn't running ended. One that passes, fails or runs out of games ends inside
    # update_test with no event, on the result that tipped it (later ones are refused), so at its newest
    # result; one stopped or deleted by hand at its newest STOP or DELETE; a bench error at its event.
    # Not the newest event: that may be the CREATE, or a worker's crash in the middle of the run.
    events = LogEvent.objects.filter(test_id=test.id).order_by('-id')
    if state == 'finished':
        event = None
    elif state == 'error':
        event = events.exclude(machine_id=0).filter(log_file='').first()
    else:
        event = events.filter(machine_id=0, summary__in=['STOP', 'DELETE']).first()
    if event:
        return event.created
    return max((row.updated for row in rows), default=None) or test.updated


def iso(when):
    return when.isoformat().replace('+00:00', 'Z') if when else None


def uci_options(options):
    # "Threads=1 Hash=16" as { "Threads": 1, "Hash": 16 }
    parsed = {}
    for name, value in re.findall(r'''([^\s=]+)=("[^"]*"|'[^']*'|\S+)''', options or ''):
        value = value.strip('"\'')
        parsed[name] = int(value) if re.fullmatch(r'-?\d+', value) else value
    return parsed


def player_name(engine, branch):
    # What nyayo's pages call a side of the test, and its games' players: the engine and the branch
    return '%s %s' % (engine, branch)


def build_v1_document(test):
    # nyayo's match schema v1, as its docs/match-schema.md (OpenBench) maps a test

    rows  = list(Result.objects.filter(test=test).select_related('machine', 'machine__user').order_by('updated'))
    count = lambda name: sum(getattr(row, name) for row in rows)

    instance           = getattr(settings, 'NYAYO_INSTANCE', 'local')
    state, sprt_result = match_state(test)
    openbench_url      = getattr(settings, 'NYAYO_OPENBENCH_URL', '').strip().rstrip('/')

    finished_at = iso(ended_at(test, state, rows)) if state not in ('waiting', 'running') else None

    sprt = stats = None
    if test.test_mode == 'SPRT':
        model = 'penta' if test.use_penta else 'tri'
        sprt  = {
            'elo0': test.elolower, 'elo1': test.eloupper, 'alpha': test.alpha, 'beta': test.beta, 'model': model,
            'llr': test.currentllr, 'lower': test.lowerllr, 'upper': test.upperllr, 'result': sprt_result,
        }
        # As the test page shows it (templatetags/mytags.py)
        lower, elo, upper = OpenBench.stats.Elo(test.results())
        stats = { 'elo': elo, 'error': max(upper - elo, elo - lower), 'model': model }

    # A machine is on the test now when its workload is this test and it was heard from in the last 5 minutes
    # (utils.getRecentMachines)
    recent = timezone.now() - datetime.timedelta(minutes=5)

    machines = []
    for row in rows:
        name = (row.machine.info or {}).get('machine_name')
        machines.append({
            'name': name if name and name != 'None' else 'machine %d' % (row.machine.id),
            'machine_id': row.machine.id, 'user': row.machine.user.username,
            'games': row.games, 'crashes': row.crashes, 'timeloss': row.timeloss, 'updated_at': iso(row.updated),
            'active': row.machine.workload == test.id and row.machine.updated >= recent,
        })

    return {
        'schema_version': 1,
        'match': {
            'id': build_match_id(test),
            'name': '%s vs %s' % (player_name(test.dev_engine, test.dev.name), test.base.name),
            'kind': 'sprt' if test.test_mode == 'SPRT' else 'games',
            'state': state,
            'producer': {
                'name': 'OpenBench', 'version': instance,
                'url': '%s/test/%d/' % (openbench_url, test.id) if openbench_url else None,
            },
            'started_at': iso(test.creation),
            'updated_at': iso(timezone.now()),
            'finished_at': finished_at,
            'host': { 'name': instance },
            'settings': {
                'tc': test.dev_time_control, 'book': test.book_name,
                'runner': { 'name': 'cutechess-ob' }, 'pgn_options': [],
                # Fixed once nyayo has the match, so only what a test can't change: not its
                # workload size (MODIFY), upload_pgns or scale_nps (both set at a first workload)
                'openbench': {
                    'test_mode': test.test_mode, 'max_games': test.max_games,
                    'base_time_control': test.base_time_control,
                    'win_adj': test.win_adj, 'draw_adj': test.draw_adj,
                    'syzygy_wdl': test.syzygy_wdl, 'syzygy_adj': test.syzygy_adj,
                    'scale_method': test.scale_method,
                    'dev_network': test.dev_netname, 'base_network': test.base_netname,
                },
            },
        },
        'subject': {
            'name': test.dev_engine, 'version': '', 'commit': test.dev.sha, 'branch': test.dev.name,
            'repo': test.dev_repo, 'bench': test.dev.bench, 'options': uci_options(test.dev_options),
        },
        'opponents': [{
            'id': 'base', 'name': test.base_engine, 'version': '', 'commit': test.base.sha, 'branch': test.base.name,
            'repo': test.base_repo, 'bench': test.base.bench, 'options': uci_options(test.base_options),
            'rating': None,
        }],
        'results': [{
            'opponent': 'base',
            'games': count('games'), 'wins': count('wins'), 'draws': count('draws'), 'losses': count('losses'),
            'penta': [count('LL'), count('LD'), count('DD'), count('DW'), count('WW')],
            # OpenBench doesn't know which side crashed or lost on time
            'timelosses': { 'subject': count('timeloss'), 'opponent': 0 },
            'crashes': { 'subject': count('crashes'), 'opponent': 0 },
        }],
        'progress': None,
        'games': None,
        'sprt': sprt,
        'stats': stats,
        'machines': machines,
    }


def build_openbench_document(test, producer_url=None):
    if producer_url is None:
        producer_url = '/test/%d/' % test.id

    result_rows = Result.objects.filter(test=test).order_by('updated')
    totals = {
        'games': 0,
        'wins': 0,
        'losses': 0,
        'draws': 0,
        'LL': 0,
        'LD': 0,
        'DD': 0,
        'DW': 0,
        'WW': 0,
        'crashes': 0,
        'timeloss': 0,
    }

    for row in result_rows:
        totals['games'] += row.games
        totals['wins'] += row.wins
        totals['losses'] += row.losses
        totals['draws'] += row.draws
        totals['LL'] += row.LL
        totals['LD'] += row.LD
        totals['DD'] += row.DD
        totals['DW'] += row.DW
        totals['WW'] += row.WW
        totals['crashes'] += row.crashes
        totals['timeloss'] += row.timeloss

    kind = 'sprt' if test.test_mode == 'SPRT' else 'games'
    state, sprt_result = match_state(test)
    if state == 'waiting':
        state = 'running'  # This shape (refused by nyayo from 0913a6c) predates the states before running

    document = {
        'schema_version': 1,
        'id': build_match_id(test),
        'kind': kind,
        'state': state,
        'updated_at': timezone.now().isoformat().replace('+00:00', 'Z'),
        'producer': {
            'kind': 'OpenBench',
            'url': producer_url,
            'instance': getattr(settings, 'NYAYO_INSTANCE', 'local'),
        },
        'subject': {
            'engine': test.dev.name,
            'name': test.dev.name,
            'repo': test.dev_repo,
            'sha': test.dev.sha,
            'bench': test.dev.bench,
            'options': test.dev_options,
            'time_control': test.dev_time_control,
            'network': test.dev_netname,
            'book': test.book_name,
        },
        'opponents': [{
            'engine': test.base.name,
            'name': test.base.name,
            'repo': test.base_repo,
            'sha': test.base.sha,
            'bench': test.base.bench,
            'options': test.base_options,
            'time_control': test.base_time_control,
            'network': test.base_netname,
        }],
        'results': [{
            'games': totals['games'],
            'wins': totals['wins'],
            'losses': totals['losses'],
            'draws': totals['draws'],
            'LL': totals['LL'],
            'LD': totals['LD'],
            'DD': totals['DD'],
            'DW': totals['DW'],
            'WW': totals['WW'],
            'crashes': totals['crashes'],
            'timeloss': totals['timeloss'],
        }],
        'sprt': {
            'lower': test.elolower,
            'upper': test.eloupper,
            'alpha': test.alpha,
            'beta': test.beta,
            'current_llr': test.currentllr,
            'lower_llr': test.lowerllr,
            'upper_llr': test.upperllr,
            'result': sprt_result,
        },
        'settings': {
            'dev_time_control': test.dev_time_control,
            'base_time_control': test.base_time_control,
            'book_name': test.book_name,
            'adjudication': test.win_adj,
            'syzygy_wdl': test.syzygy_wdl,
            'syzygy_adj': test.syzygy_adj,
            'scale_method': test.scale_method,
            'scale_nps': test.scale_nps,
        },
        'machines': [],
        'error': bool(test.error),
        'finished': bool(test.finished),
    }

    for row in result_rows:
        document['machines'].append({
            'machine_id': row.machine.id,
            'user': row.machine.user.username,
            'games': row.games,
            'wins': row.wins,
            'losses': row.losses,
            'draws': row.draws,
            'crashes': row.crashes,
            'timeloss': row.timeloss,
            'updated_at': row.updated.isoformat().replace('+00:00', 'Z'),
        })

    return document


def enqueue_report(test_id):
    if not nyayo_enabled():
        return False
    REPORT_QUEUE.put(test_id)
    return True


def enqueue_pgn(test_id, result_id, book_index, data):
    # A worker's upload (.pgn.bz2), on the games' queue: in order, behind no report
    if not nyayo_enabled():
        return False
    GAME_QUEUE.put((test_id, result_id, book_index, data))
    return True


def split_games(text):
    # A stripped upload is "<headers>\n\n<moves>\n\n" per game (Client/pgn_util.py)
    games, headers = [], None
    for block in re.split(r'\n\s*\n', text.strip()):
        block = block.strip()
        if block.startswith('['):
            headers = block
        elif headers is not None and block:
            games.append((headers, block))
            headers = None
    return games


def tag_game(headers, moves, subject_colour, opponent):
    # Which player is the engine under test: cutechess names them <engine>-dev and <engine>-base
    tags = headers
    if subject_colour:
        tags += '\n[Subject "%s"]' % (subject_colour)
    if opponent:
        tags += '\n[Opponent "%s"]' % (opponent)
    return '%s\n\n%s\n' % (tags, moves)


def rename_players(headers, dev, base):
    # cutechess's <engine>-dev and <engine>-base, as the sides' names in the match document
    def rename(match):
        name = match.group(2)
        name = dev if name.endswith('-dev') else base if name.endswith('-base') else name
        return '[%s "%s"]' % (match.group(1), name.replace('"', "'"))
    return re.sub(r'^\[(White|Black) "([^"]*)"\]', rename, headers, flags=re.M)


def subject_colour(headers):
    white = re.search(r'^\[White "([^"]*)"\]', headers, re.M)
    black = re.search(r'^\[Black "([^"]*)"\]', headers, re.M)
    if white and white.group(1).endswith('-dev'):
        return 'white'
    if black and black.group(1).endswith('-dev'):
        return 'black'
    return ''


def name_and_tag(test, data):
    # An upload as nyayo takes it. From client 39 the worker names and tags every game (Client/pgn_util.py), and the
    # bytes go as they are. An older one (the tars' uploads from before) still has cutechess's names and no tags: its
    # games are renamed and tagged here, and it is compressed again, so its sha256 is no longer the tar's.
    games  = split_games(bz2.decompress(data).decode('utf-8'))
    tagged = lambda tags: re.search(r'^\[Subject "', tags, re.M)
    if all(tagged(tags) for tags, _ in games):
        return data

    names, text = (player_name(test.dev_engine, test.dev.name), player_name(test.base_engine, test.base.name)), ''
    for tags, moves in games:
        if tagged(tags):
            text += '%s\n\n%s\n\n' % (tags, moves)
        else:
            text += tag_game(rename_players(tags, *names), moves, subject_colour(tags), 'base') + '\n'
    return bz2.compress(text.encode('utf-8'))  # The worker's layout and compression level


def report_pgn(test_id, result_id, book_index, data, schema=None):
    # A workload's upload, PUT whole to /api/matches/<id>/pgns/<result>.<book_index> as application/x-bzip2.
    # nyayo answers 202 and reads it later (its worker); 200 is the same bytes again
    if not nyayo_enabled():
        return False

    upload = '%d.%d' % (result_id, book_index)
    try:
        test    = Test.objects.get(id=test_id)
        body    = name_and_tag(test, data)
        url     = '%s/api/matches/%s/pgns/%s' % (settings.NYAYO_URL.rstrip('/'), build_match_id(test), upload)
        headers = { 'Authorization': 'Bearer %s' % settings.NYAYO_TOKEN, 'Content-Type': 'application/x-bzip2' }
    except Exception:
        logger.exception('OpenBench failed to read upload %s of test %s for nyayo', upload, test_id)
        return False

    try:
        with requests.Session() as session:
            response = put_upload(session, url, body, headers)
            # nyayo doesn't know the match (it was down for its reports): send it, then the upload again
            if response.status_code == 404 and report_test(test_id, schema):
                response = put_upload(session, url, body, headers)
        if refused(response):
            logger.error('nyayo refused upload %s of test %s: %s', upload, test_id, refused(response))
            return False
        return True
    except Exception:
        logger.exception('OpenBench failed to report upload %s of test %s to nyayo', upload, test_id)
        return False


def put_upload(session, url, body, headers):
    # A 503 is nyayo busy with games, never a refusal: sent again after its Retry-After, for as long
    # as GAME_BUSY_LIMIT seconds of waiting. Uploads wait behind it, in order; reports don't.
    waited = 0
    while True:
        response = session.put(url, data=body, headers=headers, timeout=30)
        if response.status_code != 503 or waited >= GAME_BUSY_LIMIT or REPORT_STOP.is_set():
            return response
        try:
            delay = min(max(float(response.headers.get('Retry-After', 1)), 0.1), 30)
        except ValueError:
            delay = 1
        delay = min(delay, GAME_BUSY_LIMIT - waited)
        REPORT_STOP.wait(delay)
        waited += delay


def stored_uploads(test_id):
    # A test's uploads as OpenBench keeps them, [(result id, book index, bytes)] in the order uploaded: the PGN
    # watcher's tar (Media/PGNs/<test>.pgn.tar), then any not moved into it yet (Media/<test>.<result>.<book>.pgn.bz2)
    uploads, seen = [], set()
    tar_path = os.path.join(settings.MEDIA_ROOT, 'PGNs', '%d.pgn.tar' % (test_id))
    if os.path.exists(tar_path):
        with tarfile.open(tar_path) as tar:
            for member in tar.getmembers():
                found = re.fullmatch(r'%d\.(\d+)\.(\d+)\.pgn\.bz2' % (test_id), member.name)
                if found and member.isfile():
                    key = (int(found.group(1)), int(found.group(2)))
                    # A name twice in the tar: the newer bytes, in the place of the first
                    if key in seen:
                        uploads = [x for x in uploads if x[:2] != key]
                    uploads.append((*key, tar.extractfile(member).read()))
                    seen.add(key)
    for pgn in PGN.objects.filter(test_id=test_id, processed=False).order_by('id'):
        path = os.path.join(settings.MEDIA_ROOT, pgn.filename())
        if (pgn.result_id, pgn.book_index) not in seen and os.path.exists(path):
            with open(path, 'rb') as fin:
                uploads.append((pgn.result_id, pgn.book_index, fin.read()))
            seen.add((pgn.result_id, pgn.book_index))
    return uploads


def report_uploads(test_id, schema=None):
    # Sends a test's stored uploads again, as the reporter would have (report_to_nyayo --games). Returns (sent, failed)
    sent = failed = 0
    for result_id, book_index, data in stored_uploads(test_id):
        if report_pgn(test_id, result_id, book_index, data, schema):
            sent += 1
        else:
            failed += 1
    return sent, failed


def report_test(test_id, schema=None):
    if not nyayo_enabled():
        return False

    try:
        test = Test.objects.get(id=test_id)
        document = build_match_document(test, schema)
        url = '%s/api/matches/%s' % (settings.NYAYO_URL.rstrip('/'), build_match_id(test))
        response = requests.put(
            url,
            json=document,
            headers={
                'Authorization': 'Bearer %s' % settings.NYAYO_TOKEN,
                'Content-Type': 'application/json',
            },
            timeout=5,
        )
        if refused(response):
            logger.error('nyayo refused the match of test %s: %s', test_id, refused(response))
            return False
        return True
    except Exception:
        logger.exception('OpenBench failed to report match for test %s to nyayo', test_id)
        return False


def refused(response):
    # nyayo's answer when it isn't 200, 201 or 202 (an upload taken, read later): the status and its plain-text
    # reason, which says what to fix
    if response.status_code in (200, 201, 202):
        return None
    return '%d %s' % (response.status_code, response.text.strip()[:500])


def _report_loop():
    while not REPORT_STOP.is_set():
        try:
            test_id = REPORT_QUEUE.get(timeout=1)
        except queue.Empty:
            continue
        report_test(test_id)


def _game_loop():
    # A game whose match nyayo doesn't know yet has the match sent first, from this thread (report_pgn)
    while not REPORT_STOP.is_set():
        try:
            item = GAME_QUEUE.get(timeout=1)
        except queue.Empty:
            continue

        try:
            report_pgn(*item)
        finally:
            GAME_QUEUE.task_done()


def start_report_loop():
    global REPORT_THREAD, GAME_THREAD

    if not nyayo_enabled():
        return None

    if REPORT_THREAD is not None and REPORT_THREAD.is_alive():
        return REPORT_THREAD

    REPORT_STOP.clear()
    REPORT_THREAD = threading.Thread(target=_report_loop, name='nyayo-report-loop', daemon=True)
    GAME_THREAD   = threading.Thread(target=_game_loop, name='nyayo-game-loop', daemon=True)
    REPORT_THREAD.start()
    GAME_THREAD.start()
    return REPORT_THREAD


def stop_report_loop():
    REPORT_STOP.set()
