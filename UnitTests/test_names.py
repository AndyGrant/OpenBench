#!/bin/python3

# A name for a test (ramani plans/sprt-steps.md, A name for a test), with GitHub's answers faked:
#   - when a sha is typed: the branch it is the head of (not the default if there is another), else the head branch of
#     a pull request, else the commit's first line as the test's name with the sha kept as the branch
#   - a name typed on the create page is the test's name whatever was typed
#   - a lookup that fails falls through, and the test is still made
#   - the match's name and the subject's branch in nyayo's document; older tests keep theirs
# Run from UnitTests/ with the server's requirements installed.

import os
import sys
import tempfile
import types

PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0, PARENT)

ROOT = tempfile.mkdtemp(prefix='openbench-unit-')
os.environ['DJANGO_SETTINGS_MODULE']  = 'OpenSite.settings_isolated'
os.environ['OPENBENCH_ISOLATED_ROOT'] = ROOT

import django
django.setup()

from django.core.management import call_command
call_command('migrate', verbosity=0)

from django.contrib.auth.models import User

import OpenBench.nyayo
import OpenBench.workloads.create_workload as create_workload
import OpenBench.workloads.verify_workload as verify_workload

from OpenBench.models import Engine, Profile, Test

REPO = 'https://github.com/looak/elephant'
API  = 'https://api.github.com/repos/looak/elephant'
SHA  = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
BASE = 'b' * 40

def heads_of(sha): return '/commits/%s/branches-where-head' % (sha)
def pulls_of(sha): return '/commits/%s/pulls' % (sha)

def commit(sha, message='Add a thing\n\nBench: 123456'):
    return { 'sha' : sha, 'commit' : { 'message' : message, 'tree' : { 'sha' : 't' + sha } } }

def pull(ref, repo='looak/elephant'):
    return { 'head' : { 'ref' : ref, 'repo' : { 'full_name' : repo } }, 'base' : { 'repo' : { 'full_name' : 'looak/elephant' } } }

class Github:
    # requests.get, answered from a dict of path -> JSON; a path not in it is an error, as is GitHub being down
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def __call__(self, url, headers=None, timeout=None):
        self.asked.append(url.replace(API, ''))
        answer = self.answers[url.replace(API, '')]
        if isinstance(answer, Exception): raise answer
        return types.SimpleNamespace(json=lambda: answer)

def form(dev, base='main', name=''):
    return { 'name': name, 'dev_branch': dev, 'dev_repo': REPO, 'dev_engine': 'elephant', 'dev_bench': 'Autofill',
             'dev_options': 'Threads=1 Hash=8', 'dev_network': '', 'dev_time_control': '8+0.08',
             'base_branch': base, 'base_repo': REPO, 'base_engine': 'elephant', 'base_bench': 'Autofill',
             'base_options': 'Threads=1 Hash=8', 'base_network': '', 'base_time_control': '8+0.08',
             'book_name': '8moves_v3.epd', 'upload_pgns': 'COMPACT', 'workload_size': '32', 'priority': '0',
             'throughput': '1000', 'syzygy_wdl': 'OPTIONAL', 'syzygy_adj': 'OPTIONAL', 'win_adj': 'None',
             'draw_adj': 'None', 'scale_method': 'BASE', 'scale_nps': '1000000', 'test_mode': 'SPRT',
             'test_bounds': '[0.00, 5.00]', 'test_confidence': '[0.05, 0.05]' }

def answers_for(**more):
    return { '/commits/' + SHA: commit(SHA), '/commits/' + BASE: commit(BASE), '/branches/main': { 'commit': commit(BASE) },
             '/branches/feature-y': { 'commit': commit(SHA) }, **more }

def collect(answers, dev=SHA, side='dev', **more):
    github, errors = Github(answers), []
    verify_workload.requests.get = github
    request = types.SimpleNamespace(POST={ **form(dev), **more })
    info, has_all = verify_workload.collect_github_info(errors, request, side)
    assert not errors, errors
    return info, github

def create(answers, dev, base='main', name=''):
    # As the create page makes a test, but for the form checks that need the whole config
    verify_workload.requests.get = Github(answers)
    def verified(request, kind):
        errors = []
        return errors, tuple(verify_workload.collect_github_info(errors, request, x) for x in ('dev', 'base'))
    create_workload.verify_workload = verified

    user = User.objects.get_or_create(username='unit-names')[0]
    Profile.objects.get_or_create(user=user)
    test, errors = create_workload.create_new_test(types.SimpleNamespace(POST=form(dev, base, name), user=user))
    assert not errors, errors
    return test, OpenBench.nyayo.build_match_document(test, 'v1')

def test_a_branch_where_head():
    info, _ = collect(answers_for(**{ heads_of(SHA): [{ 'name': 'feature-x' }] }))
    assert info[1:] == ('feature-x', SHA, 123456, '')

def test_a_branch_that_is_not_the_default():
    info, _ = collect(answers_for(**{ heads_of(SHA): [{ 'name': 'main' }, { 'name': 'feature-x' }], '': { 'default_branch': 'main' } }))
    assert info[1] == 'feature-x'

    # Only the default has it: that is the branch
    info, _ = collect(answers_for(**{ heads_of(SHA): [{ 'name': 'main' }] }))
    assert info[1] == 'main'

def test_a_pull_request_when_no_branch_has_it():
    # A pull request from a fork is somebody else's branch of the same name, so it is not the one
    info, _ = collect(answers_for(**{ heads_of(SHA): [], pulls_of(SHA): [pull('main', 'someone/elephant'), pull('moved-on')] }))
    assert info[1:] == ('moved-on', SHA, 123456, '')

def test_the_commits_first_line_when_nothing_has_it():
    answers = answers_for(**{ heads_of(SHA): [], pulls_of(SHA): [] })
    info, _ = collect(answers)
    assert info[1:] == (SHA, SHA, 123456, 'Add a thing')

    # A message that is only the bench line is still its first line; an empty one is no title at all
    answers['/commits/' + SHA] = commit(SHA, 'Bench: 1')
    assert collect(answers)[0][1:] == (SHA, SHA, 1, 'Bench: 1')
    answers['/commits/' + SHA] = commit(SHA, '')
    assert collect(answers, dev_bench='7')[0][1:] == (SHA, SHA, 7, '')

def test_github_down_still_gives_the_sha():
    down = ConnectionError('no route')
    info, _ = collect(answers_for(**{ heads_of(SHA): down, pulls_of(SHA): down }))
    assert info[1] == SHA and info[4] == 'Add a thing'

    # Where a list should be, an error message falls through as well
    limited = { 'message': 'API rate limit exceeded' }
    info, _ = collect(answers_for(**{ heads_of(SHA): limited, pulls_of(SHA): limited }))
    assert info[1] == SHA and info[4] == 'Add a thing'

def test_a_typed_branch_is_not_looked_up():
    info, github = collect(answers_for(), dev='feature-y')
    assert info[1:] == ('feature-y', SHA, 123456, '') and github.asked == ['/branches/feature-y']

def test_a_test_by_sha_is_named_by_its_branch():
    test, document = create(answers_for(**{ heads_of(SHA): [{ 'name': 'feature-x' }] }), SHA)
    assert test.name == '' and test.dev.name == 'feature-x' and test.dev.sha == SHA
    assert document['match']['name'] == 'elephant feature-x vs main'
    assert (document['subject']['branch'], document['subject']['commit']) == ('feature-x', SHA)

def test_a_test_with_no_branch_is_named_by_the_commit():
    test, document = create(answers_for(**{ heads_of(SHA): [], pulls_of(SHA): [] }), SHA)
    assert test.name == 'Add a thing' and test.dev.name == SHA
    assert document['match']['name'] == 'Add a thing'
    assert (document['subject']['branch'], document['subject']['commit']) == (SHA, SHA)

def test_a_test_made_with_github_down():
    down = ConnectionError('no route')
    test, document = create(answers_for(**{ heads_of(SHA): down, pulls_of(SHA): down }), SHA)
    assert test.dev.name == SHA and document['match']['name'] == 'Add a thing'

def test_a_typed_name_wins():
    answers = answers_for(**{ heads_of(SHA): [{ 'name': 'feature-x' }] })
    test, document = create(answers, SHA, name='  My own name ')
    assert test.name == 'My own name' and test.dev.name == 'feature-x'
    assert document['match']['name'] == 'My own name'

    # Also over a branch that was typed
    test, document = create(answers, 'main', name='Another')
    assert document['match']['name'] == 'Another' and document['subject']['branch'] == 'main'

def test_a_base_by_sha_gets_a_branch_but_never_a_name():
    test, document = create(answers_for(**{ heads_of(BASE): [{ 'name': 'release' }] }), 'feature-y', BASE)
    assert test.name == '' and test.base.name == 'release' and test.base.sha == BASE
    assert document['match']['name'] == 'elephant feature-y vs release'

    # With no branch it stays the sha, and the commit's line is not the test's name
    test, document = create(answers_for(**{ heads_of(BASE): [], pulls_of(BASE): [] }), 'feature-y', BASE)
    assert test.name == '' and test.base.name == BASE

def test_a_long_name_is_cut_to_nyayos_limit():
    long = 'x' * 150 + ' ' + 'y' * 150
    none = { heads_of(SHA): [], pulls_of(SHA): [] }
    answers = answers_for(**none)
    answers['/commits/' + SHA] = commit(SHA, long + '\n\nBench: 5')
    test, document = create(answers, SHA)
    assert test.name == long[:200] and len(document['match']['name']) == 200

    # The same for a name that was typed
    test, document = create(answers_for(**none), SHA, name='z' * 300)
    assert test.name == 'z' * 200 and document['match']['name'] == 'z' * 200

def test_older_tests_keep_their_rows():
    engine = Engine.objects.create(name='old-branch', source='', sha='0' * 40, bench=1)
    test   = Test.objects.create(dev=engine, base=engine, dev_engine='elephant', approved=True)
    assert test.name == ''
    assert OpenBench.nyayo.build_match_document(test, 'v1')['match']['name'] == 'elephant old-branch vs old-branch'

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for test in (test_a_branch_where_head, test_a_branch_that_is_not_the_default, test_a_pull_request_when_no_branch_has_it,
                 test_the_commits_first_line_when_nothing_has_it, test_github_down_still_gives_the_sha,
                 test_a_typed_branch_is_not_looked_up, test_a_test_by_sha_is_named_by_its_branch,
                 test_a_test_with_no_branch_is_named_by_the_commit, test_a_test_made_with_github_down,
                 test_a_typed_name_wins, test_a_long_name_is_cut_to_nyayos_limit, test_a_base_by_sha_gets_a_branch_but_never_a_name,
                 test_older_tests_keep_their_rows):
        test()
        print('PASS', test.__name__)
