import datetime
import re

from django.conf import settings
from django.utils import timezone

from OpenBench.models import LogEvent, Result, Step

# A machine's walk through a test, in the order it is drawn (ramani plans/sprt-steps.md, The walk)
WALK = (
    ('picked_up', ''),
    ('compile', 'dev'), ('compile', 'base'),
    ('bench', 'dev'), ('bench', 'base'),
    ('running', ''),
)

STATES = ('active', 'passed', 'failed')

# What a log may hold, kept: the end of the compiler's output. nyayo answers 400 above 4096 bytes of it.
LOG_KEPT = 64 * 1024


def tail(text, size):
    # The last size bytes of text, whole characters only
    data = (text or '').encode('utf-8')
    return data[-size:].decode('utf-8', errors='ignore') if len(data) > size else (text or '')


def start_walk(result):
    # A workload is handed to a machine. It passes picked up, the first one it gets. One that comes back keeps the
    # steps it has passed, so its walk doesn't flicker back to pending every few minutes. One that comes back after
    # a failure is a retry (the worker was told to try again): the failed steps wait to be tried, and their tries
    # are kept, counted until the step passes. A restart by hand is restart_walks.
    now  = timezone.now()
    rows = { (x.step, x.side) : x for x in Step.objects.filter(result=result) }

    for row in rows.values():
        if row.state == 'failed':
            clear(row, tries=row.tries)
            row.save()

    if ('picked_up', '') not in rows:
        Step.objects.create(result=result, step='picked_up', state='passed', at=now)


def restart_walks(test):
    # A test restarted by hand: every worker's walk starts over, the failures forgotten with their tries, and a
    # hold is released (it is the failed steps that hold it).
    for row in Step.objects.filter(result__test=test).exclude(step='picked_up'):
        clear(row, tries=0)
        row.save()


def clear(row, tries):
    row.state, row.at, row.seconds, row.cached, row.tries = 'pending', None, None, None, tries
    row.detail = row.log = row.blame = row.effect = ''
    row.nodes = row.nps = row.retry_at = None
    row.evidence = []


def record_step(result, form):
    # What the worker says of a step as it starts or ends (clientReportStep). Returns the row, or None when
    # it says nothing that matters. A step passed stays passed when the walk comes round again: the worker
    # reports it active at every workload, and a re-pass changes nothing.
    key = (form.get('step', ''), form.get('side', ''))
    if key not in WALK or key == ('picked_up', '') or form.get('state') not in STATES:
        return None

    step, _ = Step.objects.get_or_create(result=result, step=key[0], side=key[1])
    state   = form['state']

    if step.state == 'passed' and state != 'failed':
        return None

    # A step that passed on an earlier workload and fails now: the same binary gave two answers (judge)
    step.was_passed = step.state == 'passed'

    step.state, step.at = state, timezone.now()
    step.detail = form.get('detail', '')[:512]

    if state == 'failed':
        step.tries += 1
        step.log    = tail(form.get('log', ''), LOG_KEPT)
    else:
        step.log = ''

    if state == 'passed':
        step.detail = ''

    # Measurements are only the worker's to give; a step started has none yet
    step.seconds = number(form.get('seconds'), float) if state != 'active' else None
    step.cached  = form.get('cached') == 'true' if form.get('cached') in ('true', 'false') else None
    step.nodes   = number(form.get('nodes'), int)
    step.nps     = number(form.get('nps'), int)

    # A verdict belongs to the failure it was made for
    step.blame, step.effect, step.retry_at, step.evidence = '', '', None, []
    step.save()
    return step


def number(value, kind):
    try:
        return kind(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def walk_document(rows, iso):
    # A machine's steps as nyayo's machines[].steps, in the order of the walk. A step with no row is pending.
    # Nothing, for a machine that never reported any (a Result from before the steps).
    rows = { (x.step, x.side) : x for x in rows }
    if not rows:
        return None

    steps = []
    for key, side in WALK:
        row, entry = rows.get((key, side)), { 'step': key }
        if side:
            entry['side'] = side
        if row is None or row.state == 'pending':
            entry['state'] = 'pending'
            steps.append(entry)
            continue

        entry['state'] = row.state
        if row.state == 'failed' and row.blame == 'unclear' and row.tries >= TRIES_UNCLEAR:
            row.effect = leaving_effect(row)  # Written again each time: it changes as other workers come and go
        for name, value in (('at', iso(row.at)), ('seconds', None if row.seconds is None else round(row.seconds, 1)),
                            ('cached', row.cached), ('detail', row.detail), ('log', tail(row.log, 4096)),
                            ('nodes', row.nodes), ('nps', row.nps), ('tries', row.tries or None),
                            ('blame', row.blame), ('evidence', row.evidence), ('effect', row.effect),
                            ('retry_at', iso(row.retry_at))):
            if value not in (None, '', []):
                entry[name] = value
        steps.append(entry)
    return steps


## The verdict (ramani plans/sprt-steps.md, Whose failure it is, What each verdict does). The server works it out when
## a stage (the compiles, or the benches) has ended on both engines of a machine, so a rule changes without a client.

RETRY_SECONDS = 300 # A worker in trouble tries again after this long
STOPPED       = 'Stopped: ' # What the event of a test stopped by a verdict starts with
TRIES_UNCLEAR = 2   # A failure nobody can place gets one more try on the machine, then the machine leaves the test

# What a compiler's output says of the machine, not the source: no space, compiler not found, permission denied
MACHINE_LOG = re.compile(r'no space left on device|permission denied|command not found|: not found\b|'
                         r'compiler[^\n]*not found|cannot find (?:the )?compiler|^make: [^\s:]+: no such file or directory',
                         re.I | re.M)
SOURCE_LOG  = re.compile(r'^\S+?:\d+(?::\d+)?:\s*(?:fatal )?error:', re.M)
KILLED_LOG  = re.compile(r'\bkilled\b|terminated by signal|signal \d+|\bsignal terminated', re.I)


def retry_seconds():
    return int(getattr(settings, 'STEP_RETRY_SECONDS', RETRY_SECONDS))


def spoken(seconds):
    # 300 as "5 minutes"
    if seconds >= 60:
        minutes = round(seconds / 60)
        return '%d minute%s' % (minutes, '' if minutes == 1 else 's')
    return '%d second%s' % (seconds, '' if seconds == 1 else 's')


def machine_name(machine):
    name = (machine.info or {}).get('machine_name')
    return name if name and name != 'None' else 'machine %d' % (machine.id)


def compile_kind(row):
    # What a failed compile was: machine (the log names the machine), source (an error with a file and a line),
    # killed (by a signal), missing (a private engine's artifact, which isn't judged) or other
    text = '%s\n%s' % (row.log, row.detail)
    if re.match(r'Artifact .* missing', row.detail):
        return 'missing'
    if MACHINE_LOG.search(text):
        return 'machine'
    if SOURCE_LOG.search(text):
        return 'source'
    if KILLED_LOG.search(text):
        return 'killed'
    return 'other'


def bench_kind(row):
    # slow (over its 60 seconds), wrong (not the commit's bench), nondeterministic, execute (failed to run) or other
    text = row.detail.lower()
    for kind, words in (('slow', ('exceeded', 'over 60')), ('wrong', ('wrong bench',)),
                        ('nondeterministic', ('non-deterministic',)), ('execute', ('failed to execute',))):
        if any(word in text for word in words):
            return kind
    return 'other'


def kind_of(row):
    return compile_kind(row) if row.step == 'compile' else bench_kind(row)


def source_location(row):
    # The file and line of a compiler's first error, as "src/eval/mobility.cpp:212"
    found = re.search(r'^(\S+?:\d+)(?::\d+)?:\s*(?:fatal )?error:', row.log or '', re.M)
    return re.sub(r'^(?:\.\./)+', '', found.group(1)) if found else None


def side_word(side):
    return side.capitalize()


def other_side(side):
    return 'base' if side == 'dev' else 'dev'


def point(points_at, text):
    return { 'points_at' : points_at, 'text' : text }


def decide(step, was_passed=False):
    # (blame, evidence) for a failed step, from the first row of the plan's table that fits, or None where nothing
    # is judged. The other engine on the same machine is the control; the other machines' rows on the same step
    # are what else is known of this engine.
    result = step.result
    other  = Step.objects.filter(result=result, step=step.step, side=other_side(step.side)).first()
    others = list(Step.objects.filter(result__test_id=result.test_id, step=step.step, side=step.side).exclude(result=result))
    kind   = kind_of(step)
    side, control = side_word(step.side), side_word(other_side(step.side))
    passed = other is not None and other.state == 'passed'
    failed = other is not None and other.state == 'failed'
    matched_elsewhere = [x for x in others if x.state == 'passed']

    if kind == 'missing':
        return None

    if step.step == 'compile':
        if kind == 'machine':
            return 'worker', [point('worker', 'The compiler\'s output names the machine, not the source.')]
        if matched_elsewhere:
            return 'worker', [point('worker', '%s compiled on %s, so the source is fine.' % (
                side, ', '.join(machine_name(x.result.machine) for x in matched_elsewhere)))]
        if kind == 'source':
            if passed:
                return 'engine', [point('engine', 'A compile error in the source, with a file and a line.'),
                                  point('engine', '%s compiled on this worker, so its compiler and disk are fine.' % (control))]
            if failed:
                return 'worker', [point('worker', 'A compile error with a file and a line, but %s failed here too.' % (control.lower())),
                                  point('worker', 'Both engines failing on one machine says more of the machine than the source.')]
        same = [x for x in others if x.state == 'failed' and compile_kind(x) == kind]
        if same:
            return 'engine', [point('engine', 'The same failure as %s, on another machine.' % (
                ', '.join(machine_name(x.result.machine) for x in same)))]
        evidence = []
        if kind == 'killed':
            evidence.append(point('worker', 'A killed compiler isn\'t a compile error: nothing wrong in the source was found.'))
        if passed:
            evidence.append(point('engine', '%s compiled on this worker, so only %s is affected.' % (control, side.lower())))
        evidence.append(point('either', 'No other worker has tried %s.' % (side.lower()) if not others else
                                        'Other workers failed %s differently.' % (side.lower())))
        return 'unclear', evidence

    # A bench
    if kind == 'slow':
        if failed and bench_kind(other) == 'slow':
            return 'worker', [point('worker', '%s timed out too, on the same machine.' % (control))]
        if passed:
            return 'engine', [point('engine', '%s benched within its time on this worker.' % (control))]
    elif kind == 'wrong':
        if was_passed:
            return 'engine', [point('engine', 'It matched its bench on this worker earlier: the same binary gave two answers.')]
        if failed and bench_kind(other) == 'wrong':
            return 'unclear', [point('either', 'Both engines gave a wrong bench here.')]
        if passed and matched_elsewhere:
            return 'unclear', [point('engine', '%s matched its bench on this worker.' % (control)),
                               point('worker', '%s matched on %s, so this machine may be building it differently.' % (
                                   side, ', '.join(machine_name(x.result.machine) for x in matched_elsewhere)))]
        if passed:
            return 'engine', [point('engine', '%s matched its bench on this worker.' % (control)),
                              point('either', "Only this worker has tried, so a build difference on it isn't ruled out.")]
    elif kind in ('nondeterministic', 'execute'):
        if passed:
            return 'engine', [point('engine', '%s benched fine on this worker.' % (control))]
        if failed:
            return 'worker', [point('worker', '%s failed to bench on this worker too.' % (control))]
    return 'unclear', [point('either', 'Nothing here says whose it is.')]


def others_able(test, result):
    # Whether another machine could still play the test: it is on it now (its workload is the test and it was heard
    # from in the last 5 minutes, as nyayo's `active`) and nothing of its walk has failed
    recent = timezone.now() - datetime.timedelta(minutes=5)
    return Result.objects.filter(test=test, machine__workload=test.id, machine__updated__gte=recent
                                 ).exclude(id=result.id).exclude(steps__state='failed').exists()


def games_played(test):
    return sum(Result.objects.filter(test=test).values_list('games', flat=True))


def retry_in(step, seconds):
    step.retry_at = timezone.now() + datetime.timedelta(seconds=seconds)


def enact(step, blame, evidence):
    # What a verdict does to the step: writes it into the row. True when the test is to be stopped.
    result, test = step.result, step.result.test
    machine = machine_name(result.machine)
    control = side_word(other_side(step.side))
    step.blame, step.evidence, step.retry_at = blame, evidence, None
    seconds = retry_seconds()

    if blame == 'engine':
        step.effect = 'The test stops, with its games kept.' if games_played(test) else 'The test stops.'
        if Step.objects.filter(result=result, step=step.step, side=other_side(step.side), state__in=('passed', 'failed')).exists():
            step.effect += ' %s %s still ran, as the control.' % (step.step.capitalize(), control.lower())
    elif blame == 'worker':
        retry_in(step, seconds)
        step.effect = '%s tries again in %s.' % (machine, spoken(seconds))
    elif step.tries < TRIES_UNCLEAR:
        retry_in(step, seconds)
        step.effect = '%s tries once more in %s, then leaves the test.' % (machine, spoken(seconds))
    else:
        step.effect = leaving_effect(step)
    step.save()
    return blame == 'engine'


def leaving_effect(step):
    # What a machine that has left the test means for it, as it stands now: whether anyone else can play it changes
    machine = machine_name(step.result.machine)
    if others_able(step.result.test, step.result):
        return '%s leaves the test, which another worker can still play.' % (machine)
    return 'The test is held: no more tries from %s, no verdict, and no expiry.' % (machine)


def headline(step):
    # What is wrong, in a few words: "Dev doesn't compile"
    side, kind = side_word(step.side), kind_of(step)
    if step.step == 'compile':
        return { 'source' : "%s doesn't compile", 'killed' : "%s's compile was killed", 'machine' : "%s couldn't be compiled here",
                 }.get(kind, '%s failed to compile') % (side)
    return { 'slow' : "%s's bench runs over 60 seconds", 'wrong' : "%s's bench doesn't match its commit",
             'nondeterministic' : "%s isn't deterministic", 'execute' : '%s failed to run its bench',
             }.get(kind, "%s's bench failed") % (side)


def stop_test(step):
    # An engine's failure stops the test (with nothing played, a failed start: nyayo.match_state). The event dates
    # the stop, and is what OpenBench's own list of events shows.
    result, test = step.result, step.result.test
    if test.finished or test.deleted:
        return
    test.finished = True
    test.save()
    LogEvent.objects.create(author=result.machine.user.username, summary=(STOPPED + headline(step))[:128],
                            log_file='', machine_id=result.machine.id, test_id=test.id)


def settle(result, step, side, was_passed=False):
    # Called after a step ended, passed or failed. Judges the failed steps of its stage once both engines are done,
    # and returns (what the worker is answered, whether a verdict was made or changed). The answer is { 'stop' : True },
    # { 'retry_after' : seconds }, or {} where there is nothing to say (a stage still going, a step that passed,
    # trouble that isn't judged). A stage reported again answers the same and changes nothing.
    rows = list(Step.objects.filter(result=result, step=step).select_related('result__machine__user', 'result__test'))
    if len(rows) != 2 or any(x.state not in ('passed', 'failed') for x in rows):
        return {}, False

    changed = False
    for row in rows:
        if row.state == 'failed' and not row.blame:
            if decided := decide(row, was_passed and row.side == side):
                changed = True
                if enact(row, *decided):
                    stop_test(row)

    for row in rows:
        changed = judge_again(row) or changed

    if any(x.state == 'failed' and x.blame == 'engine' for x in rows):
        return { 'stop' : True }, changed

    waits = [x.retry_at for x in rows if x.state == 'failed' and x.retry_at]
    if waits:
        return { 'retry_after' : max(1, round((max(waits) - timezone.now()).total_seconds())) }, changed
    if any(x.state == 'failed' and x.blame == 'unclear' for x in rows):
        return { 'retry_after' : retry_seconds() }, changed # Away from the test, as long as the server keeps it so
    return {}, changed


def judge_again(row):
    # A new machine's failure is what a can't-tell on another machine was waiting for. True where one changed.
    changed = False
    for old in Step.objects.filter(result__test_id=row.result.test_id, step=row.step, side=row.side, state='failed',
                                   blame='unclear').exclude(result=row.result).select_related('result__machine__user', 'result__test'):
        if (decided := decide(old)) and decided[0] != 'unclear':
            changed = True
            if enact(old, *decided):
                stop_test(old)
    return changed


def left_tests(machine):
    # The tests a machine has left, until a restart: it failed a step nobody could place, and had its one more try
    return list(Step.objects.filter(result__machine=machine, state='failed', blame='unclear', tries__gte=TRIES_UNCLEAR
                                    ).values_list('result__test_id', flat=True))


## What the verdicts make of a test, for nyayo (OpenBench/nyayo.py): its state and match.verdict

def failed_rows(test, **where):
    return list(Step.objects.filter(result__test=test, state='failed', **where
                                    ).select_related('result__machine').order_by('at', 'id'))


def engine_failure(test):
    # The failed steps an engine verdict was made of, which is what stopped the test
    return failed_rows(test, blame='engine')


def held(test):
    # A failure nobody can place, on a machine that has left the test, and no other machine able to play it
    return [x for x in failed_rows(test, blame='unclear', tries__gte=TRIES_UNCLEAR) if not others_able(test, x.result)]


def worker_trouble(test):
    # Every machine that took the test is in trouble of its own: each has a step failed on the worker's account
    rows    = failed_rows(test, blame='worker')
    results = Result.objects.filter(test=test, steps__isnull=False).distinct()
    if not rows or any(x.id not in { y.result_id for y in rows } for x in results):
        return []
    return rows


def verdict_document(test, state):
    # match.verdict, in OpenBench's words, when the state comes from a failure; None otherwise
    if state in ('failed_prechecks', 'error'):
        rows = engine_failure(test)
    elif state == 'held':
        rows = held(test)
    elif state == 'waiting':
        rows = worker_trouble(test)
    else:
        rows = []
    if not rows:
        return None

    first = rows[0]
    kind  = kind_of(first)
    side  = side_word(first.side)
    other = side_word(other_side(first.side))
    names = []
    for row in rows:
        name = machine_name(row.result.machine)
        if name not in names:
            names.append(name)
    played = 'Nothing was played.' if state == 'failed_prechecks' else 'Games were played, and are kept.'

    if state == 'waiting':
        return { 'blame' : 'worker', 'summary' : 'Nothing is known against the engines, but no worker can run this yet',
                 'detail' : 'Every worker that tried is in trouble of its own. The test starts by itself as soon as one gets through its checks.',
                 'where' : None, 'seen_on' : names }

    if state == 'held':
        tried  = Step.objects.filter(result__test=test, step=first.step, side=first.side, state__in=('passed', 'failed')
                                     ).exclude(result=first.result).exists()
        detail = "A second worker's result settles it by itself; otherwise restart it on OpenBench once you've looked."
        if kind == 'killed':
            detail = 'It might be %s short of memory, or %s having grown too big to build. %s' % (names[0], side.lower(), detail)
        return { 'blame' : 'unclear', 'detail' : detail, 'where' : None, 'seen_on' : names,
                 'summary' : headline(first) + ('' if tried else ', and no other worker has tried it') }

    if first.step == 'compile' and kind == 'source':
        detail = '%s, and %s compiled beside it. %s' % (
            'Every worker that tried gave the same error' if len(names) > 1 else 'The compiler found an error in the source',
            other.lower(), played)
    elif kind == 'wrong' and 'two answers' in ' '.join(x['text'] for x in first.evidence):
        detail = ("%s matched its bench on this worker before, and gave another answer now: the same binary gave "
                  "two answers, so it isn't deterministic across runs.") % (side)
    elif kind == 'wrong':
        detail = ("%s benched as expected on the same machine, so the worker is measuring correctly. Either the commit's "
                  "bench line is stale, or %s isn't deterministic across builds.") % (other, side.lower())
    else:
        detail = ' '.join(x['text'] for x in first.evidence)
    return { 'blame' : 'engine', 'summary' : headline(first), 'detail' : detail,
             'where' : source_location(first) if kind == 'source' else None, 'seen_on' : names }
