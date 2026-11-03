#!/bin/python3

# The fork's workers upload each game with its final players and tags (nyayo's game database):
#   - pgn_util names <engine>-dev and <engine>-base <engine> <branch>, tags Subject and Opponent, keeps Termination
#   - cutechess still plays under <engine>-dev and <engine>-base, so the result counts are unchanged
#   - the reporter sends an upload already tagged as it is, and still renames and tags an older one, once
# Run from UnitTests/ with the Client's requirements installed (Client/requirements.txt).

import importlib.util
import os
import sys
import types

# Needed to include from ../Client/*.py
PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.append(os.path.join(PARENT, 'Client'))

import pgn_util

PLAYERS = { 'dev' : 'Weiss feature "x"', 'base' : 'Weiss master' }

def tags_of(text):
    return pgn_util.pgn_header_list(x for x in text.split('\n') if x)

def test_names_and_tags():

    games = list(pgn_util.pgn_iterator('example3.pgn'))
    assert [h['White'] for h, _ in games[:2]] == ['Weiss-dev', 'Weiss-base']

    for headers, _ in games:
        headers['Termination'] = 'adjudication'
        dev_white = headers['White'].endswith('-dev')
        for compact in (True, False):

            tags = tags_of(pgn_util.pgn_strip_headers(dict(headers), compact, PLAYERS))
            dev, base = "Weiss feature 'x'", 'Weiss master'  # A quote in a name becomes ', as the reporter does
            assert (tags['White'], tags['Black']) == ((dev, base) if dev_white else (base, dev)), tags
            assert tags['Subject'] == ('white' if dev_white else 'black'), tags
            assert tags['Opponent'] == 'base', tags
            assert tags['Termination'] == 'adjudication', tags

            # Without players, as upstream: cutechess's names, no tags of the fork's, Termination kept
            plain = tags_of(pgn_util.pgn_strip_headers(dict(headers), compact))
            assert plain['White'] == headers['White'] and 'Subject' not in plain and 'Opponent' not in plain
            assert plain['Termination'] == 'adjudication'

    # Subject and Opponent come last, after every tag upstream keeps
    order = [x.split()[0][1:] for x in pgn_util.pgn_strip_headers(dict(games[0][0]), False, PLAYERS).split('\n')]
    assert order[-2:] == ['Subject', 'Opponent'], order

def test_counts_unchanged():

    # cutechess is still given <engine>-<side>: update_results reads its lines by word position
    sys.argv = sys.argv[:1]
    import worker

    workload = { 'test' : { 'type' : 'GAMES', 'syzygy_wdl' : 'DISABLED' } }
    for side in ('dev', 'base'):
        workload['test'][side] = {
            'options' : 'Threads=1 Hash=16', 'network' : None, 'private' : False,
            'engine' : 'Weiss', 'name' : 'feature x', 'time_control' : 'N=1000',
        }
    config = types.SimpleNamespace(workload=workload)
    for side in ('dev', 'base'):
        settings = worker.Cutechess.engine_settings(config, 'Weiss-%s' % (side), side, 1.0, 0)
        assert settings.endswith(' name=Weiss-%s' % (side)), settings

    lines = [
        'Finished game 1 (Weiss-dev vs Weiss-base): 1-0 {White mates}',
        'Finished game 2 (Weiss-base vs Weiss-dev): 1/2-1/2 {Draw by adjudication}',
        'Finished game 3 (Weiss-dev vs Weiss-base): 0-1 {White loses on time}',
        'Finished game 4 (Weiss-base vs Weiss-dev): 0-1 {Black mates}',
    ]
    results = { 'games' : {}, 'trinomial' : [0, 0, 0], 'pentanomial' : [0] * 5,
                'crashes' : 0, 'timelosses' : 0, 'illegals' : 0 }
    for line in lines:
        worker.Cutechess.update_results(results, line)

    assert results['trinomial'] == [1, 1, 2], results     # L, D, W from dev's side
    assert results['pentanomial'] == [0, 0, 1, 1, 0], results
    assert results['timelosses'] == 1 and results['crashes'] == 0, results

def load_reporter():

    # OpenBench/nyayo.py without a Django project: only its game functions are used
    for name in ('OpenBench', 'OpenBench.stats', 'OpenBench.models', 'OpenBench.steps'):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules['OpenBench'].__path__ = []
    for model in ('LogEvent', 'PGN', 'Result', 'Step', 'Test'):
        setattr(sys.modules['OpenBench.models'], model, None)

    spec   = importlib.util.spec_from_file_location('nyayo_reporter', os.path.join(PARENT, 'OpenBench', 'nyayo.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_reporter_once():

    import bz2
    nyayo = load_reporter()
    test  = types.SimpleNamespace(dev_engine='Weiss', dev=types.SimpleNamespace(name='feature x'),
                                  base_engine='Weiss', base=types.SimpleNamespace(name='master'))
    names = ('Weiss feature x', 'Weiss master')

    # An older upload, cutechess's names: every game renamed and tagged on the server, in the worker's layout
    with open('example3.pgn', 'rb') as fin:
        older = bz2.compress(fin.read())
    body  = nyayo.name_and_tag(test, older)
    games = nyayo.split_games(bz2.decompress(body).decode())
    assert body != older and len(games) == len(nyayo.split_games(bz2.decompress(older).decode())) == 34
    for tags, _ in games:
        sent = tags_of(tags)
        colour = sent['Subject']
        assert (sent['White'], sent['Black']) == (names if colour == 'white' else names[::-1]), sent
        assert sent['Opponent'] == 'base' and tags.count('[Subject ') == 1 and tags.count('[Opponent ') == 1
    assert bz2.decompress(body).decode().endswith('\n\n')

    # Sent again, or uploaded named and tagged by the worker: the same bytes, no second rename or tag
    assert nyayo.name_and_tag(test, body) is body
    assert nyayo.name_and_tag(test, nyayo.name_and_tag(test, older)) == body  # And compressed the same each time

    headers = pgn_util.pgn_header_list(x for x in games[0][0].split('\n') if x)
    headers['White'], headers['Black'] = 'Weiss-dev', 'Weiss-base'
    upload = bz2.compress(('%s\n\n%s\n\n' % (pgn_util.pgn_strip_headers(headers, True, dict(zip(('dev', 'base'), names))),
                                              games[0][1])).encode())
    assert nyayo.name_and_tag(test, upload) is upload

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for test in (test_names_and_tags, test_counts_unchanged, test_reporter_once):
        test()
        print('PASS', test.__name__)
