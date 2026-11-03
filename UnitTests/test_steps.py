#!/bin/python3

# A machine's walk through a test (ramani plans/sprt-steps.md, The walk):
#   - a step's row per Result, and what the worker's reports do to it: a step passed stays passed when the walk
#     comes round again, a failure is counted, a worker back after a failure starts over
#   - the walk as nyayo's machines[].steps: all six steps in order, pending where there is no row, a log cut to its
#     last 4096 bytes whole, nothing for a machine that never reported a step
#   - a test is waiting until a worker has passed running
#   - the worker takes both engines through a stage and raises what failed once both are done
# Run from UnitTests/ with the server's and the Client's requirements installed.

import os
import sys
import tempfile
import types

PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0, PARENT)
sys.path.insert(0, os.path.join(PARENT, 'Client'))

ROOT = tempfile.mkdtemp(prefix='openbench-unit-')
os.environ['DJANGO_SETTINGS_MODULE']  = 'OpenSite.settings_isolated'
os.environ['OPENBENCH_ISOLATED_ROOT'] = ROOT

import django
django.setup()

from django.core.management import call_command
call_command('migrate', verbosity=0)

from django.contrib.auth.models import User

import OpenBench.nyayo
import OpenBench.steps as steps

from OpenBench.models import Engine, Machine, Result, Step, Test

def make_result():
    user    = User.objects.create(username='unit%d' % (User.objects.count()))
    machine = Machine.objects.create(user=user, info={})
    engine  = Engine.objects.create(name='x', source='', sha='0' * 40, bench=1)
    test    = Test.objects.create(dev=engine, base=engine, approved=True)
    return Result.objects.create(test=test, machine=machine)

def states(result):
    return { (x.step, x.side) : x.state for x in Step.objects.filter(result=result) }

def report(result, step, side, state, **form):
    return steps.record_step(result, { 'step' : step, 'side' : side, 'state' : state, **form })

def test_a_step_passed_stays_passed():
    result = make_result()
    steps.start_walk(result)
    assert states(result) == { ('picked_up', '') : 'passed' }

    assert report(result, 'compile', 'dev', 'active')
    assert report(result, 'compile', 'dev', 'passed', seconds='41.2', cached='false')
    row = Step.objects.get(result=result, step='compile', side='dev')
    assert (row.state, row.seconds, row.cached) == ('passed', 41.2, False)

    # The next workload walks it again: nothing changes, so nothing is worth a report
    steps.start_walk(result)
    assert report(result, 'compile', 'dev', 'active') is None
    assert report(result, 'compile', 'dev', 'passed', seconds='0', cached='true') is None
    row.refresh_from_db()
    assert (row.state, row.seconds, row.cached) == ('passed', 41.2, False)

    # What the server has no step for, or no state for, is nothing
    assert report(result, 'compile', 'sideways', 'active') is None
    assert report(result, 'compile', 'dev', 'sleeping') is None
    assert report(result, 'picked_up', '', 'failed') is None

def test_a_failure_is_counted_and_a_restart_starts_over():
    result = make_result()
    steps.start_walk(result)
    report(result, 'compile', 'dev', 'passed')
    report(result, 'compile', 'base', 'passed')
    report(result, 'bench', 'dev', 'active')
    report(result, 'bench', 'dev', 'failed', detail='Wrong bench: 2, expected 1', seconds='3')
    row = Step.objects.get(result=result, step='bench', side='dev')
    assert (row.state, row.tries, row.detail) == ('failed', 1, 'Wrong bench: 2, expected 1')

    # A step passed can still fail on a later workload
    report(result, 'compile', 'base', 'failed', detail='no space left', log='make: write error')
    assert Step.objects.get(result=result, step='compile', side='base').state == 'failed'

    # Handed out again after a failure: the walk starts over, the tries stay
    steps.start_walk(result)
    assert states(result) == {
        ('picked_up', '') : 'passed', ('compile', 'dev') : 'pending', ('compile', 'base') : 'pending',
        ('bench', 'dev') : 'pending', }
    assert Step.objects.get(result=result, step='bench', side='dev').tries == 1
    assert Step.objects.get(result=result, step='compile', side='base').log == ''

    # ... and a worker that fails it again counts it again
    report(result, 'bench', 'dev', 'failed', detail='again')
    assert Step.objects.get(result=result, step='bench', side='dev').tries == 2

def test_the_walk_as_nyayo_takes_it():
    iso = OpenBench.nyayo.iso
    result = make_result()
    assert steps.walk_document(Step.objects.filter(result=result), iso) is None  # A Result from before the steps

    steps.start_walk(result)
    report(result, 'compile', 'dev', 'passed', seconds='41', cached='false')
    report(result, 'bench', 'dev', 'passed', seconds='38', nodes='1000', nps='2500000')
    report(result, 'compile', 'base', 'failed', detail='error: x', log='€' * 3000)

    walk = steps.walk_document(Step.objects.filter(result=result), iso)
    assert [(x['step'], x.get('side')) for x in walk] == [
        ('picked_up', None), ('compile', 'dev'), ('compile', 'base'), ('bench', 'dev'), ('bench', 'base'), ('running', None)]
    assert [x['state'] for x in walk] == ['passed', 'passed', 'failed', 'passed', 'pending', 'pending']
    assert walk[1]['cached'] is False and walk[1]['seconds'] == 41 and walk[1]['at'].endswith('Z')
    assert (walk[3]['nodes'], walk[3]['nps']) == (1000, 2500000)
    assert walk[4] == { 'step' : 'bench', 'side' : 'base', 'state' : 'pending' }
    assert walk[2]['tries'] == 1 and walk[2]['detail'] == 'error: x'

    # The log's last 4096 bytes, no character cut in two (nyayo answers 400 above that)
    log = walk[2]['log']
    assert len(log.encode('utf-8')) <= 4096 and len(log.encode('utf-8')) > 4090 and set(log) == { '€' }

def test_waiting_until_a_worker_reaches_running():
    result = make_result()
    test   = result.test
    assert OpenBench.nyayo.match_state(test) == ('waiting', None)

    steps.start_walk(result)
    report(result, 'compile', 'dev', 'passed')
    assert OpenBench.nyayo.match_state(test) == ('waiting', None)
    report(result, 'running', '', 'active')
    assert OpenBench.nyayo.match_state(test) == ('waiting', None)
    report(result, 'running', '', 'passed')
    assert OpenBench.nyayo.match_state(test) == ('running', None)

    # A test from before the steps that has games is running
    other = make_result(); other.games = 2; other.save()
    assert OpenBench.nyayo.match_state(other.test) == ('running', None)

def test_both_engines_through_a_stage():
    import worker
    from client import BadVersionException

    calls = []
    def run(name, fail=None):
        def inner():
            calls.append(name)
            if fail: raise fail
            return name
        return inner

    assert worker.both_engines(run('dev'), run('base')) == ['dev', 'base']

    calls.clear()
    try: worker.both_engines(run('dev', RuntimeError('dev')), run('base'))
    except RuntimeError as error: assert str(error) == 'dev'
    else: assert False, 'the failure was not raised'
    assert calls == ['dev', 'base']  # Base ran beside the failed dev, as the control

    calls.clear()
    try: worker.both_engines(run('dev', RuntimeError('dev')), run('base', RuntimeError('base')))
    except RuntimeError as error: assert str(error) == 'dev'  # Dev's first
    assert calls == ['dev', 'base']

    # A bad version is the client's to deal with at once
    calls.clear()
    try: worker.both_engines(run('dev', BadVersionException()), run('base'))
    except BadVersionException: pass
    else: assert False, 'a bad version was held back'
    assert calls == ['dev']

def test_a_step_is_never_the_workloads_failure():
    import worker
    from client import BadVersionException

    config = types.SimpleNamespace(workload={ 'test' : { 'id' : 1 } })
    reporter = worker.ServerReporter

    def lost(*args, **kwargs): raise ConnectionError('the server is away')
    original, reporter.report = reporter.report, staticmethod(lost)
    try:
        reporter.report_step(config, 'compile', 'dev', 'active')  # Caught and forgotten

        def old(*args, **kwargs): raise BadVersionException()
        reporter.report = staticmethod(old)
        try: reporter.report_step(config, 'compile', 'dev', 'active')
        except BadVersionException: pass
        else: assert False, 'a bad version was swallowed'
    finally:
        reporter.report = original

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for test in (test_a_step_passed_stays_passed, test_a_failure_is_counted_and_a_restart_starts_over,
                 test_the_walk_as_nyayo_takes_it, test_waiting_until_a_worker_reaches_running,
                 test_both_engines_through_a_stage, test_a_step_is_never_the_workloads_failure):
        test()
        print('PASS', test.__name__)
