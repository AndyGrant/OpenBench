#!/bin/python3

# The client's part of the verdict (ramani plans/sprt-steps.md, OpenBench): the answer to a step that ended is
# remembered, and the blacklist has a time per test, dropped when it is due.
# Run from UnitTests/ with the Client's requirements installed.

import os
import sys
import time
import types

PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0, os.path.join(PARENT, 'Client'))


def test_the_blacklist_has_a_time_per_test():
    import worker

    config = types.SimpleNamespace(blacklist={}, workload={ 'test' : { 'id' : 7 } }, answer={})
    assert worker.blacklisted(config) == []

    # What the server asked, and the default where it said nothing
    config.answer = { 'retry_after' : 120 }
    worker.leave_for_a_while(config)
    assert config.blacklist[7] - time.time() > 100
    assert worker.blacklisted(config) == [7]

    config.answer = {}
    worker.leave_for_a_while(config)
    assert 290 < config.blacklist[7] - time.time() <= 300

    # A test stopped has nothing to wait for
    config.answer = { 'stop' : True }
    worker.leave_for_a_while(config)
    assert 7 not in config.blacklist

    # An entry is dropped when it's due
    config.blacklist = { 7 : time.time() - 1, 8 : time.time() + 60 }
    assert worker.blacklisted(config) == [8] and list(config.blacklist) == [8]

def test_the_answer_is_what_the_worker_remembers():
    import worker

    class Response:
        def json(self): return { 'retry_after' : 45 }

    config = types.SimpleNamespace(workload={ 'test' : { 'id' : 1 } }, answer={})
    original, worker.ServerReporter.report = worker.ServerReporter.report, staticmethod(lambda *args, **kwargs: Response())
    try:
        worker.ServerReporter.report_step(config, 'compile', 'dev', 'failed')
        assert config.answer == { 'retry_after' : 45 }
        worker.ServerReporter.report_step(config, 'compile', 'base', 'passed')  # An answer isn't forgotten by the next
        assert config.answer == { 'retry_after' : 45 }
    finally:
        worker.ServerReporter.report = original


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for name, test in list(globals().items()):
        if name.startswith('test_') and callable(test):
            test()
            print('PASS', name)
