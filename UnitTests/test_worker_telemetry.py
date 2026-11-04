#!/bin/python3

# What the worker tells the server about itself: the round trip of its last call (rtt_ms) and its GPUs (gpus).
# Neither may ever fail a request. Run from UnitTests/ with the Client's requirements installed.

import itertools
import os
import sys
import types

PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0, os.path.join(PARENT, 'Client'))


class Reply:
    def json(self): return {}


def test_the_round_trip_is_sent_with_the_next_calls(monkeypatch):
    import worker

    sent  = {}
    ticks = itertools.cycle([10.0, 10.2504]) # every call takes 250.4 ms
    monkeypatch.setattr(worker.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(worker.requests, 'post', lambda target, **kw: sent.update(target=target, **kw) or Reply())
    monkeypatch.setattr(worker, 'LAST_RTT_MS', None)

    config = types.SimpleNamespace(machine_id=1, secret_token='s', server='http://x', workload={ 'test' : { 'id' : 7 } })

    # Nothing measured yet: nothing sent. The first call is measured: an integer, in milliseconds
    worker.ServerReporter.report(config, 'clientHeartbeat', {})
    assert 'rtt_ms' not in sent['data']
    assert worker.LAST_RTT_MS == 250 and isinstance(worker.LAST_RTT_MS, int)

    # ... and sent with the three calls that carry it, but not with the others
    worker.ServerReporter.report(config, 'clientHeartbeat', {})
    assert sent['data']['rtt_ms'] == 250
    worker.ServerReporter.report(config, 'clientSubmitResults', {})
    assert sent['data']['rtt_ms'] == 250
    worker.ServerReporter.report(config, 'clientReportStep', {})
    assert 'rtt_ms' not in sent['data']

    config.blacklist = {}
    worker.server_request_workload(config)
    assert sent['data']['rtt_ms'] == 250 and sent['target'].endswith('clientGetWorkload')


def test_a_failed_call_is_not_a_measurement(monkeypatch):
    import worker

    def fail(*args, **kw): raise worker.requests.ConnectionError()
    monkeypatch.setattr(worker.requests, 'post', fail)
    monkeypatch.setattr(worker, 'LAST_RTT_MS', 42)

    config = types.SimpleNamespace(machine_id=1, secret_token='s', server='http://x')
    try: worker.ServerReporter.report(config, 'clientHeartbeat', {})
    except worker.requests.ConnectionError: pass
    assert worker.LAST_RTT_MS == 42


def test_gpus_are_names_and_any_failure_is_none(monkeypatch):
    import worker

    lspci = [
        '00:02.0 VGA compatible controller: Intel Corporation UHD Graphics',
        '00:14.0 USB controller: Intel Corporation USB 3.0',
        '01:00.0 3D controller: NVIDIA Corporation GA104 [GeForce RTX 3070]',
    ]
    monkeypatch.setattr(worker.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(worker.platform, 'release', lambda: '6.1.0-generic')
    monkeypatch.setattr(worker, 'command_lines', lambda command: lspci)
    assert worker.detect_gpus() == ['Intel Corporation UHD Graphics', 'NVIDIA Corporation GA104 [GeForce RTX 3070]']

    # Under WSL, nvidia-smi is asked first
    monkeypatch.setattr(worker.platform, 'release', lambda: '5.15.0-microsoft-standard-WSL2')
    smi = ['GPU 0: NVIDIA GeForce RTX 4070 (UUID: GPU-1234)']
    monkeypatch.setattr(worker, 'command_lines', lambda command: smi if command[0] == 'nvidia-smi' else lspci)
    assert worker.detect_gpus() == ['NVIDIA GeForce RTX 4070']

    # Windows: the names as printed
    monkeypatch.setattr(worker.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(worker, 'command_lines', lambda command: ['NVIDIA GeForce RTX 4070'])
    assert worker.detect_gpus() == ['NVIDIA GeForce RTX 4070']

    # A missing tool, a timeout or anything else is an empty list
    monkeypatch.undo()
    def boom(*args, **kw): raise FileNotFoundError()
    monkeypatch.setattr(worker.subprocess, 'run', boom)
    assert worker.command_lines(['lspci']) == []
    assert worker.detect_gpus() == []
