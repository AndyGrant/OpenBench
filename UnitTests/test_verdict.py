#!/bin/python3

# Whose failure it is, and what the verdict does (ramani plans/sprt-steps.md, Whose failure it is and What each
# verdict does): a test for every row of the first table, in the order of the plan, then of the second:
#   - the verdict of a failed step, from the log, the other engine on the same worker, and the other workers
#   - what it does: an engine's failure stops the test (a failed start with nothing played, an error with games), a
#     worker's is retried, one nobody can place gets one more try and then the worker leaves; held when no worker is left
#   - the answer to the worker, the retry that keeps tries and the restart by hand that forgets them
#   - match.verdict in nyayo's words, and OpenBench's own page
# Run from UnitTests/ with the server's and the Client's requirements installed.

import os
import sys
import tempfile
import time
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

import OpenBench.nyayo as nyayo
import OpenBench.steps as steps

from OpenBench.models import Engine, LogEvent, Machine, Result, Step, Test

NO_SPACE = 'cc1plus: fatal error: error writing to /tmp/ccR2x1.s: No space left on device\nmake: *** [makefile:48: search.o] Error 1'
SOURCE   = "../src/eval/mobility.cpp:212:18: error: 'attacks_bb' was not declared in this scope\nmake: *** [makefile:48: mobility.o] Error 1"
KILLED   = 'g++: fatal error: Killed signal terminated program cc1plus\ncompilation terminated.\nmake: *** [makefile:48: search.o] Error 1'
OTHER    = 'make: *** [makefile:48: search.o] Error 2'

WRONG    = 'Wrong bench: 53681270, expected 53681269'
SLOW     = 'Bench Exceeded Max Duration'
NONDET   = 'Non-Deterministic Benches'
EXECUTE  = 'Failed to Execute Benchmark'


def new_test():
    engine = Engine.objects.create(name='x', source='', sha='0' * 40, bench=1)
    return Test.objects.create(dev=engine, base=engine, approved=True)

def new_worker(test, name):
    user    = User.objects.create(username='%s%d' % (name, User.objects.count()))
    machine = Machine.objects.create(user=user, info={ 'machine_name' : name })
    result  = Result.objects.create(test=test, machine=machine, workloads=1)
    steps.start_walk(result)
    return result

def report(result, step, side, state, **form):
    # What the view does with a report: records it, and settles a stage that has ended
    row = steps.record_step(result, { 'step' : step, 'side' : side, 'state' : state, **form })
    if state in ('passed', 'failed') and step in ('compile', 'bench'):
        return steps.settle(result, step, side, getattr(row, 'was_passed', False))[0]
    return {}

def ok(result, step, side='dev'):
    return report(result, step, side, 'passed', seconds='1')

def fail(result, step, side, detail='x', log=''):
    # The worker's stage: the failed step, then the other engine beside it, which the caller reports with ok() or fail()
    return report(result, step, side, 'failed', detail=detail, log=log)

def row(result, step, side):
    return Step.objects.get(result=result, step=step, side=side)

def reload(test):
    return Test.objects.get(id=test.id)

def verdict(result, step, side):
    found = row(result, step, side)
    return found.blame, [x['points_at'] for x in found.evidence]


# The first table, a test for every row

def test_compile_the_log_names_the_machine():
    for log in (NO_SPACE, 'make: g++: No such file or directory', 'bash: g++: command not found',
                'cc1plus: fatal error: ./x.o: Permission denied'):
        test = new_test(); hunt = new_worker(test, 'hunt')
        fail(hunt, 'compile', 'dev', log=log)
        answer = ok(hunt, 'compile', 'base')
        assert verdict(hunt, 'compile', 'dev')[0] == 'worker', log
        assert answer == { 'retry_after' : 300 } and not reload(test).finished

def test_compile_another_worker_has_passed_this_step():
    # Whatever the failure looks like, even an error with a file and a line
    for log in (SOURCE, KILLED, OTHER):
        test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
        ok(tor, 'compile', 'dev'); ok(tor, 'compile', 'base')
        fail(hunt, 'compile', 'dev', log=log); ok(hunt, 'compile', 'base')
        assert verdict(hunt, 'compile', 'dev')[0] == 'worker', log
        assert not reload(test).finished

def test_compile_an_error_with_a_file_and_a_line():
    # The other engine compiled on the same worker: the engine's
    test = new_test(); hunt = new_worker(test, 'hunt')
    fail(hunt, 'compile', 'dev', log=SOURCE)
    assert row(hunt, 'compile', 'dev').blame == ''  # Not judged until the other engine has been through the stage
    answer = ok(hunt, 'compile', 'base')
    assert verdict(hunt, 'compile', 'dev') == ('engine', ['engine', 'engine'])
    assert answer == { 'stop' : True } and reload(test).finished
    assert nyayo.match_state(reload(test)) == ('failed_prechecks', None)

    # The other engine failed too: the worker's
    test = new_test(); hunt = new_worker(test, 'hunt')
    fail(hunt, 'compile', 'dev', log=SOURCE)
    answer = fail(hunt, 'compile', 'base', log=SOURCE)
    assert verdict(hunt, 'compile', 'dev')[0] == 'worker' and verdict(hunt, 'compile', 'base')[0] == 'worker'
    assert answer == { 'retry_after' : 300 } and not reload(test).finished

def test_compile_killed_or_anything_else():
    for log in (KILLED, OTHER):
        # Another worker failed the same way: the engine's
        test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
        fail(tor, 'compile', 'dev', log=log); ok(tor, 'compile', 'base')
        assert row(tor, 'compile', 'dev').blame == 'unclear'  # Nobody else had tried when tor failed
        fail(hunt, 'compile', 'dev', log=log)
        answer = ok(hunt, 'compile', 'base')
        assert verdict(hunt, 'compile', 'dev')[0] == 'engine' and answer == { 'stop' : True }

        # ... and tor's can't-tell was waiting for exactly that
        assert verdict(tor, 'compile', 'dev')[0] == 'engine'
        assert nyayo.match_state(reload(test)) == ('failed_prechecks', None)

        # No other worker has tried: can't tell, whatever the other engine did
        test = new_test(); hunt = new_worker(test, 'hunt')
        fail(hunt, 'compile', 'dev', log=log)
        answer = ok(hunt, 'compile', 'base')
        assert verdict(hunt, 'compile', 'dev')[0] == 'unclear'
        assert answer == { 'retry_after' : 300 } and not reload(test).finished

def test_bench_over_60_seconds():
    test = new_test(); hunt = new_worker(test, 'hunt')
    ok(hunt, 'compile', 'dev'); ok(hunt, 'compile', 'base')

    # Both over: the machine is slow, the worker's
    fail(hunt, 'bench', 'dev', SLOW); answer = fail(hunt, 'bench', 'base', SLOW)
    assert verdict(hunt, 'bench', 'dev')[0] == 'worker' and answer == { 'retry_after' : 300 } and not reload(test).finished

    # Base passed beside it: the engine's
    test = new_test(); hunt = new_worker(test, 'hunt')
    ok(hunt, 'compile', 'dev'); ok(hunt, 'compile', 'base')
    fail(hunt, 'bench', 'dev', SLOW); answer = ok(hunt, 'bench', 'base')
    assert verdict(hunt, 'bench', 'dev')[0] == 'engine' and answer == { 'stop' : True }

def test_bench_wrong():
    # Wrong on both engines: can't tell
    test = new_test(); hunt = new_worker(test, 'hunt')
    fail(hunt, 'bench', 'dev', WRONG); answer = fail(hunt, 'bench', 'base', WRONG)
    assert verdict(hunt, 'bench', 'dev')[0] == 'unclear' and answer == { 'retry_after' : 300 }

    # Base matched, and another worker has matched this engine: can't tell
    test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
    ok(tor, 'bench', 'dev'); ok(tor, 'bench', 'base')
    fail(hunt, 'bench', 'dev', WRONG); answer = ok(hunt, 'bench', 'base')
    assert verdict(hunt, 'bench', 'dev')[0] == 'unclear' and not reload(test).finished

    # Base matched, and none has matched this engine: the engine's
    test = new_test(); hunt = new_worker(test, 'hunt')
    fail(hunt, 'bench', 'dev', WRONG); answer = ok(hunt, 'bench', 'base')
    assert verdict(hunt, 'bench', 'dev') == ('engine', ['engine', 'either']) and answer == { 'stop' : True }
    assert nyayo.match_state(reload(test)) == ('failed_prechecks', None)

def test_bench_wrong_on_a_worker_that_matched_earlier_is_the_engines():
    test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
    ok(tor, 'bench', 'dev'); ok(tor, 'bench', 'base')  # Which alone would make it can't-tell
    ok(hunt, 'bench', 'dev'); ok(hunt, 'bench', 'base')
    steps.start_walk(hunt)
    fail(hunt, 'bench', 'dev', WRONG); answer = ok(hunt, 'bench', 'base')
    assert verdict(hunt, 'bench', 'dev')[0] == 'engine' and answer == { 'stop' : True }
    assert 'two answers' in row(hunt, 'bench', 'dev').evidence[0]['text']

def test_bench_non_deterministic_or_failed_to_execute():
    for detail in (NONDET, EXECUTE):
        test = new_test(); hunt = new_worker(test, 'hunt')
        fail(hunt, 'bench', 'dev', detail); answer = ok(hunt, 'bench', 'base')
        assert verdict(hunt, 'bench', 'dev')[0] == 'engine' and answer == { 'stop' : True }, detail

        test = new_test(); hunt = new_worker(test, 'hunt')
        fail(hunt, 'bench', 'dev', detail); answer = fail(hunt, 'bench', 'base', detail)
        assert verdict(hunt, 'bench', 'dev')[0] == 'worker' and answer == { 'retry_after' : 300 }, detail

def test_a_missing_artifact_is_not_judged():
    test = new_test(); hunt = new_worker(test, 'hunt')
    fail(hunt, 'compile', 'dev', detail='Artifact dev missing', log='{}'); answer = ok(hunt, 'compile', 'base')
    assert row(hunt, 'compile', 'dev').blame == '' and answer == {} and not reload(test).finished

def test_the_other_engine_is_awaited():
    # A stage is judged once it has ended on both engines, not before
    test = new_test(); hunt = new_worker(test, 'hunt')
    assert fail(hunt, 'compile', 'dev', log=SOURCE) == {}
    report(hunt, 'compile', 'base', 'active')
    assert row(hunt, 'compile', 'dev').blame == '' and not reload(test).finished


# The second table

def test_an_engine_failure_with_games_is_an_error():
    test = new_test(); hunt = new_worker(test, 'hunt')
    hunt.games = 12; hunt.save()
    ok(hunt, 'compile', 'dev'); ok(hunt, 'compile', 'base')
    fail(hunt, 'bench', 'dev', WRONG); answer = ok(hunt, 'bench', 'base')
    assert answer == { 'stop' : True } and reload(test).finished
    assert nyayo.match_state(reload(test)) == ('error', None)
    assert 'games kept' in row(hunt, 'bench', 'dev').effect

    event = LogEvent.objects.get(test_id=test.id)
    assert event.summary.startswith(steps.STOPPED) and event.log_file == '' and event.machine_id == hunt.machine_id
    assert nyayo.ended_at(reload(test), 'error', [hunt]) == event.created

def test_a_worker_failure_goes_on_and_retries():
    test = new_test(); hunt = new_worker(test, 'hunt')
    fail(hunt, 'compile', 'dev', log=NO_SPACE); answer = ok(hunt, 'compile', 'base')
    found = row(hunt, 'compile', 'dev')
    assert answer == { 'retry_after' : 300 } and found.retry_at and found.effect == 'hunt tries again in 5 minutes.'
    assert not reload(test).finished and nyayo.match_state(reload(test)) == ('waiting', None)

    # Every machine in trouble of its own: the verdict says so, and the state is unchanged
    document = steps.verdict_document(reload(test), 'waiting')
    assert document['blame'] == 'worker' and document['seen_on'] == ['hunt']
    tor = new_worker(test, 'tor')
    assert steps.verdict_document(reload(test), 'waiting') is None  # tor has not failed anything

def test_a_retry_keeps_its_tries_and_a_restart_by_hand_forgets_them():
    test = new_test(); hunt = new_worker(test, 'hunt')
    ok(hunt, 'compile', 'dev')
    fail(hunt, 'compile', 'base', log=NO_SPACE); answer = ok(hunt, 'bench', 'dev')
    assert row(hunt, 'compile', 'base').tries == 1

    # The worker is handed the test again, as it was told: the passed step stays, the failed one waits, with its tries
    steps.start_walk(hunt)
    assert Step.objects.filter(result=hunt, step='compile', side='dev').get().state == 'passed'
    base = row(hunt, 'compile', 'base')
    assert (base.state, base.tries, base.blame, base.log) == ('pending', 1, '', '')
    fail(hunt, 'compile', 'base', log=NO_SPACE)
    assert row(hunt, 'compile', 'base').tries == 2

    # ... until it passes, and then the count is what it took
    steps.start_walk(hunt)
    report(hunt, 'compile', 'base', 'active'); ok(hunt, 'compile', 'base')
    assert (row(hunt, 'compile', 'base').state, row(hunt, 'compile', 'base').tries) == ('passed', 2)

    # A restart by hand starts every worker's walk over, tries and all
    tor = new_worker(test, 'tor')
    fail(tor, 'compile', 'dev', log=NO_SPACE)
    steps.restart_walks(test)
    states = { (x.result.machine.info['machine_name'], x.step, x.side) : (x.state, x.tries) for x in Step.objects.filter(result__test=test) }
    assert states['hunt', 'picked_up', ''] == ('passed', 0)
    assert all(value == ('pending', 0) for key, value in states.items() if key[1] != 'picked_up'), states

def test_nobody_can_place_it_one_more_try_then_held():
    test = new_test(); hunt = new_worker(test, 'hunt')

    # First: one more try
    fail(hunt, 'compile', 'dev', log=KILLED); answer = ok(hunt, 'compile', 'base')
    first = row(hunt, 'compile', 'dev')
    assert answer == { 'retry_after' : 300 } and first.retry_at and 'once more' in first.effect
    assert nyayo.match_state(reload(test)) == ('waiting', None) and left(hunt) == []

    # Second: hunt leaves the test, and with no worker left, the test is held
    steps.start_walk(hunt)
    fail(hunt, 'compile', 'dev', log=KILLED); answer = ok(hunt, 'compile', 'base')
    second = row(hunt, 'compile', 'dev')
    assert second.tries == 2 and second.retry_at is None and 'held' in second.effect
    assert answer == { 'retry_after' : 300 }
    assert nyayo.match_state(reload(test)) == ('held', None) and not reload(test).finished
    assert left(hunt) == [test.id]

    document = steps.verdict_document(reload(test), 'held')
    assert document['blame'] == 'unclear' and document['seen_on'] == ['hunt']
    assert document['summary'] == "Dev's compile was killed, and no other worker has tried it"
    assert nyayo.build_match_document(reload(test))['match']['state'] == 'held'
    assert nyayo.build_match_document(reload(test))['match']['finished_at'] is None

    # Restarted by hand: the hold goes with the failures
    steps.restart_walks(test)
    assert nyayo.match_state(reload(test)) == ('waiting', None) and left(hunt) == []

def leave(result):
    # Fails a killed compile, is handed the test again for its one more try, and fails it again
    fail(result, 'compile', 'dev', log=KILLED); ok(result, 'compile', 'base')
    steps.start_walk(result)
    fail(result, 'compile', 'dev', log=KILLED); ok(result, 'compile', 'base')

def left(result):
    return steps.left_tests(result.machine)

def test_a_second_worker_settles_a_held_test():
    # The other fails the same way: the engine's, and the test stops
    test = new_test(); hunt = new_worker(test, 'hunt')
    leave(hunt)
    assert nyayo.match_state(reload(test))[0] == 'held'
    tor = new_worker(test, 'tor')
    assert nyayo.match_state(reload(test))[0] == 'waiting'  # A worker able to play it: no longer held
    fail(tor, 'compile', 'dev', log=KILLED); answer = ok(tor, 'compile', 'base')
    assert answer == { 'stop' : True } and verdict(hunt, 'compile', 'dev')[0] == 'engine'
    assert nyayo.match_state(reload(test)) == ('failed_prechecks', None)
    document = steps.verdict_document(reload(test), 'failed_prechecks')
    assert sorted(document['seen_on']) == ['hunt', 'tor']

    # The other compiles it: hunt's was the worker's, and it may try again
    test = new_test(); hunt = new_worker(test, 'hunt')
    leave(hunt)
    tor = new_worker(test, 'tor')
    ok(tor, 'compile', 'dev'); ok(tor, 'compile', 'base')
    assert verdict(hunt, 'compile', 'dev')[0] == 'worker' and row(hunt, 'compile', 'dev').retry_at
    assert left(hunt) == [] and not reload(test).finished

def test_nobody_can_place_it_but_another_worker_can_play():
    test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
    leave(hunt)
    assert 'goes on with the other workers' in row(hunt, 'compile', 'dev').effect
    assert nyayo.match_state(reload(test)) == ('waiting', None)
    assert left(hunt) == [test.id]

def filter_valid_workloads_unchecked(request, machine):
    # Only the part of get_workload's filter that concerns the steps
    import OpenBench.utils
    return OpenBench.utils.get_active_tests().exclude(id__in=steps.left_tests(machine))

def test_get_workload_filter_keeps_the_others():
    test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
    leave(hunt)
    ids = lambda machine: [x.id for x in filter_valid_workloads_unchecked(None, machine)]
    assert test.id not in ids(hunt.machine) and test.id in ids(tor.machine)


# The document

def test_the_verdicts_in_nyayos_words():
    test = new_test(); hunt = new_worker(test, 'hunt'); tor = new_worker(test, 'tor')
    for worker in (hunt, tor):
        fail(worker, 'compile', 'dev', log=SOURCE); ok(worker, 'compile', 'base')
    stopped = reload(test)
    document = nyayo.build_match_document(stopped)
    assert document['match']['state'] == 'failed_prechecks' and document['match']['finished_at']
    assert document['match']['verdict'] == {
        'blame' : 'engine', 'summary' : "Dev doesn't compile",
        'detail' : 'Every worker that tried gave the same error, and base compiled beside it. Nothing was played.',
        'where' : 'src/eval/mobility.cpp:212', 'seen_on' : ['hunt', 'tor'] }
    step = next(x for x in document['machines'][0]['steps'] if x['step'] == 'compile' and x['side'] == 'dev')
    assert step['blame'] == 'engine' and step['effect'].startswith('The test stops.') and step['tries'] == 1
    assert [x['points_at'] for x in step['evidence']] == ['engine', 'engine']

    # A passing test has no verdict
    assert 'verdict' not in nyayo.build_match_document(reload(new_test()))['match']

    # OpenBench's own page: a failed start, with its reason
    import OpenBench.templatetags.mytags as tags
    assert tags.testResultColour(stopped) == 'start'
    assert tags.startProblem(stopped).startswith("Failed start: Dev doesn't compile.")
    assert tags.startProblem(new_test()) == ''


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for name, test in list(globals().items()):
        if name.startswith('test_') and callable(test):
            test()
            print('PASS', name)
