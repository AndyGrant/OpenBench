#!/bin/python3

# A test, an SPSA tune and a datagen are each made as the create page makes them (GitHub's answers faked), reported to
# nyayo, handed to a worker, and shown on OpenBench's own pages, on upstream's models with the fork's on top:
#   - the workload a worker is handed has what the worker's fastchess command needs, for each kind
#   - a tune has its SPSA run and parameters, and its workload says how many pairs a worker plays
#   - the match document builds for each (nyayo is told a tune and a datagen as `games` matches)
#   - the create pages, the index and each workload's page render
# Run from UnitTests/ with the server's requirements installed.

import os
import sys
import types

import test_names as N  # sets up Django on a database of its own, and has the faked GitHub

from django.contrib.auth.models import User
from django.test import Client

import OpenBench.nyayo
import OpenBench.workloads.create_workload as create_workload
import OpenBench.workloads.get_workload as get_workload

from OpenBench.models import Machine, Profile, Result, Step, Test

def common(dev, base='main'):
    form = N.form(dev, base)
    form.update({ 'info': '', 'book_name': '8moves_v3.epd' })
    return form

def user():
    user = User.objects.get_or_create(username='unit-kinds')[0]
    Profile.objects.update_or_create(user=user, defaults={ 'enabled': True, 'approver': True, 'superuser': True })
    return user

def make(kind):

    N.verify_workload.requests.get = N.Github(N.answers_for())
    form = common('feature-y')

    if kind == 'TEST':
        make_one = create_workload.create_new_test

    if kind == 'TUNE':
        form.update({ 'spsa_inputs': 'Tempo, int, 20, 0, 50, 2, 0.002\nAggr, float, 1.5, 0, 4, 0.2, 0.002',
                      'spsa_reporting_type': 'BATCHED', 'spsa_distribution_type': 'SINGLE', 'spsa_alpha': '0.602',
                      'spsa_gamma': '0.101', 'spsa_A_ratio': '0.1', 'spsa_iterations': '100', 'spsa_pairs_per': '4' })
        make_one = create_workload.create_new_tune

    if kind == 'DATAGEN':
        form.update({ 'datagen_max_games': '64', 'datagen_custom_genfens': '', 'datagen_play_reverses': 'YES',
                      'info': '' })
        make_one = create_workload.create_new_datagen

    request = types.SimpleNamespace(POST=form, user=user())
    test, errors = make_one(request)
    assert not errors, errors
    test.approved = True
    test.save()
    return test

def machine(concurrency=4):
    info = { 'supported': ['elephant'], 'concurrency': concurrency, 'physical_cores': concurrency, 'sockets': 1,
             'syzygy_max': 0, 'noisy': False, 'focus': [], 'only': [], 'ram_total_mb': 8192 }
    return Machine.objects.create(user=user(), info=info)

def hand_out(test):
    worker = machine()
    given  = get_workload.get_workload(types.SimpleNamespace(POST=types.SimpleNamespace(getlist=lambda _: [])), worker)
    assert given['workload']['test']['id'] == test.id, given
    result = Result.objects.get(test=test, machine=worker)
    assert result.workloads == 1 and Step.objects.get(result=result).step == 'picked_up'
    return given['workload']

def test_a_test_is_handed_out():
    test = make('TEST')
    work = hand_out(test)
    assert work['test']['type'] == 'SPRT' or work['test']['type'] == 'GAMES', work['test']['type']
    assert work['test']['dev']['engine'] == 'elephant' and work['test']['book']['name'] == '8moves_v3.epd'
    assert work['distribution']['runner-count'] >= 1 and work['distribution']['rounds-per-runner'] >= 1
    assert OpenBench.nyayo.build_match_document(test, 'v1')['match']['settings']['runner'] == { 'name': 'fastchess' }
    assert test.upload_pgns in ('COMPACT', 'VERBOSE')

def test_a_tune_is_handed_out():
    test = make('TUNE')
    run  = test.spsa_run
    assert (run.iterations, run.pairs_per, run.parameters.count()) == (100, 4, 2)
    assert [x.name for x in run.parameters.order_by('index')] == ['Tempo', 'Aggr']
    work = hand_out(test)
    assert work['test']['type'] == 'SPSA', work['test']['type']
    assert OpenBench.nyayo.build_match_document(test, 'v1')['match']['kind'] == 'games'

def test_a_datagen_is_handed_out():
    test = make('DATAGEN')
    work = hand_out(test)
    assert work['test']['type'] == 'DATAGEN', work['test']['type']
    assert OpenBench.nyayo.build_match_document(test, 'v1')['match']['kind'] == 'games'

def test_the_pages_render():
    client = Client()
    client.force_login(user())
    for path in ('/index/', '/test/new/', '/tune/new/', '/datagen/new/', '/manage/engines/', '/manage/books/',
                 '/machines/', '/events/'):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
    for test in Test.objects.order_by('id'):
        kind = { 'SPSA': 'tune', 'DATAGEN': 'datagen' }.get(test.test_mode, 'test')
        response = client.get('/%s/%d/' % (kind, test.id))
        assert response.status_code == 200, (test.id, response.status_code)
        assert b'Traceback' not in response.content

    # The create page offers this lab's engine and its books, from the database
    page = client.get('/test/new/').content.decode()
    assert '<option value="elephant">elephant</option>' in page and '8moves_v3.epd' in page

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for test in (test_a_test_is_handed_out, test_a_tune_is_handed_out, test_a_datagen_is_handed_out, test_the_pages_render):
        test()
        print('PASS', test.__name__)
