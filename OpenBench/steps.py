from django.utils import timezone

from OpenBench.models import Step

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
    # A workload is handed to a machine. It passes picked up, the first one it gets. One that comes back
    # keeps the steps it has passed, so its walk doesn't flicker back to pending every few minutes; one that
    # comes back after a failure (a restart by hand) starts over.
    now  = timezone.now()
    rows = { (x.step, x.side) : x for x in Step.objects.filter(result=result) }

    if any(x.state == 'failed' for x in rows.values()):
        for row in rows.values():
            if (row.step, row.side) != ('picked_up', ''):
                row.state, row.at, row.seconds, row.cached = 'pending', None, None, None
                row.detail = row.log = row.blame = row.effect = ''
                row.nodes = row.nps = row.retry_at = None
                row.evidence = []
                row.save()
        if ('picked_up', '') in rows:
            rows['picked_up', ''].delete()
            del rows['picked_up', '']

    if ('picked_up', '') not in rows:
        Step.objects.create(result=result, step='picked_up', state='passed', at=now)


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
        for name, value in (('at', iso(row.at)), ('seconds', None if row.seconds is None else round(row.seconds, 1)),
                            ('cached', row.cached), ('detail', row.detail), ('log', tail(row.log, 4096)),
                            ('nodes', row.nodes), ('nps', row.nps), ('tries', row.tries or None),
                            ('blame', row.blame), ('evidence', row.evidence), ('effect', row.effect),
                            ('retry_at', iso(row.retry_at))):
            if value not in (None, '', []):
                entry[name] = value
        steps.append(entry)
    return steps
