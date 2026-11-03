#!/bin/python3

# The migrations of upstream and the fork, joined (OpenBench/migrations/): the fork's 0002-0008 run first, upstream's
# 0002-0017 after them, then the fork's 0018 and 0019. They must apply on a database that already holds rows, in
# each state the fork's databases are in, and end where a fresh database does:
#   - at d9cdb95, the fork before this merge: its chain applied, with tests, workloads, steps and an SPSA tune
#   - bobby's, older: applied up to 0006_result_base_nodes_result_base_time_and_more (it made that one itself),
#     before the steps and the names
#   - older than the models: the first migration only, and the tables lack columns the models have
# After each: every row is still there, an engine's source is upstream's zipball form, the books of this lab and its
# Elephant engine are in the database, a test from before fastchess says it was played by cutechess-ob, and the tables
# are the ones a fresh database has. Run from UnitTests/ with the server's requirements installed.

import os
import sys
import tempfile

PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0, PARENT)

ROOT = tempfile.mkdtemp(prefix='openbench-unit-')
os.environ['DJANGO_SETTINGS_MODULE']  = 'OpenSite.settings_isolated'
os.environ['OPENBENCH_ISOLATED_ROOT'] = ROOT

import django
django.setup()

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = 'OpenBench'

# Books/<name>.json of the fork at d9cdb95: the books this lab offered, and their shas
LAB_BOOKS = {
    '2moves_v1.epd'          : '7bec98239836f219dc41944a768c0506abed950aaec48da69a0782643e90f237',
    '3moves_FRC.epd'         : '6bf81e1ada6a3306bbc8356f7bca1e2984a2828d658799992d5443b7179c934d',
    '4moves_noob.epd'        : '4be746a91e3f8af0c9344b1e72d611e9fcfe486843867a55760970a4896f284d',
    '8moves_v3.epd'          : '1f055af431656f09ee6a09d2448e0b876125f78bb7b404fca2031c403a1541e5',
    'DFRC.epd'               : '648c447ef40614a44d13b78911e81470d8ddb0d3b2711c1b180e990871f5db4f',
    'Endgames.epd'           : '71c7477ca8c8fb097bb565794d8b5ed8754532f8fb499e9d8b1d397692302a6a',
    'Pohl.epd'               : 'b3e64e0dab84cf451a9ac7ef031f5a2bbcf16c7e21be95298fb03cbf021f5466',
    'Pohl.pgn'               : 'aaa7559c5d94e592fe5cca3586cb099d8fc5f13428d4ce84afc4b97811241c7e',
    'UHO_4060_v2.epd'        : '36f2ec751ab78def6be1307430cbe2cd2ba65ade8d2aaae8f10e3df7d0ea83e1',
    'UHO_4060_vB.epd'        : '68c58a5f6a5e068a30376efa19a6bcd78f8ec8bb67ad984dd8d156abfa81de96',
    'UHO_4060_vT.epd'        : 'f5da53b91b85f5ddc72c352522a8056ab8bbf0058b67d799c4ca96effd5d5f26',
    'UHO_Lichess_4852_v1.epd': '7a7f6470615a69c6cf23d565417701d38732876f480af90d67b42abade35644a',
}

OLD_SOURCE = 'https://github.com/looak/elephant/archive/%s.zip'  # What the fork's engines have

def use_new_database(name):
    connection.close()
    connection.settings_dict['NAME'] = os.path.join(ROOT, name + '.sqlite3')

def migrate(target=None):
    # To a migration of OpenBench, or all of them, the other apps' too
    call_command('migrate', *([APP, target] if target else []), verbosity=0, interactive=False)

def state_apps(target):
    return MigrationExecutor(connection).loader.project_state((APP, target)).apps

def schema():
    # Every OpenBench table: column name -> (type, not null, default); the order of the columns is not part of it
    with connection.cursor() as cursor:
        tables = [x for (x,) in cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'OpenBench_%'")]
        return { table : { row[1] : row[2:5] for row in cursor.execute('PRAGMA table_info("%s")' % table).fetchall() }
                 for table in tables }

def fresh_schema():
    use_new_database('fresh')
    migrate()
    return schema()

def seed(target):

    # Rows as the fork's code at that state makes them, through the models of that state
    apps = state_apps(target)
    User, Machine, Engine, Test, Result = (apps.get_model(*x) for x in (
        ('auth', 'User'), (APP, 'Machine'), (APP, 'Engine'), (APP, 'Test'), (APP, 'Result')))

    user    = User.objects.create(username='unit-migrations')
    machine = Machine.objects.create(user=user, info={})
    dev     = Engine.objects.create(name='feature', source=OLD_SOURCE % ('a' * 40), sha='a' * 40, bench=123)
    base    = Engine.objects.create(name='main',    source=OLD_SOURCE % ('b' * 40), sha='b' * 40, bench=123)
    test    = Test.objects.create(dev=dev, base=base, dev_engine='elephant', base_engine='elephant', approved=True,
                                  book_name='8moves_v3.epd', games=40, wins=20, losses=10, draws=10)
    Result.objects.create(test=test, machine=machine, games=40, wins=20, losses=10, draws=10)

    # A tune of the old SPSA, kept in a field of its own, which upstream's 0006 moves into rows
    Test.objects.create(dev=dev, base=dev, dev_engine='elephant', base_engine='elephant', test_mode='SPSA', approved=True,
                        spsa={ 'Alpha' : 0.602, 'Gamma' : 0.101, 'A_ratio' : 0.1, 'iterations' : 100, 'pairs_per' : 8,
                               'reporting_type' : 'BATCHED', 'distribution_type' : 'SINGLE',
                               'parameters' : { 'Tempo' : { 'index' : 0, 'float' : False, 'start' : 20.0, 'value' : 22.0,
                                                            'min' : 0.0, 'max' : 50.0, 'c_end' : 2.0, 'r_end' : 0.002,
                                                            'c' : 4.0, 'a_end' : 0.1, 'a' : 0.2 } } })
    return apps

def check_applied(target, steps):

    from OpenBench.models import Book, Engine, EngineConfig, Result, Step, Test

    assert not [x for x in MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes())], \
        'migrations left to apply'

    tests = Test.objects.order_by('id')
    assert tests.count() == 2 and Result.objects.count() == 1 and Engine.objects.count() == 2
    assert [x.games for x in tests] == [40, 0] and tests[0].wins == 20
    assert tests[0].name == '' and tests[0].info == '' and all(x.runner == 'cutechess-ob' for x in tests)

    # Upstream's zipball form for an engine's source, as its 0011 makes them
    assert {x.source for x in Engine.objects.all()} == {
        'https://api.github.com/repos/looak/elephant/zipball/%s' % (x * 40) for x in 'ab' }

    # The old SPSA tune is rows now
    run = tests[1].spsa_run
    assert (run.iterations, run.pairs_per, run.parameters.count()) == (100, 8, 1)
    assert run.parameters.get().name == 'Tempo' and run.parameters.get().value == 22.0

    # The books of this lab, with the shas it had them by, and its engine, as upstream keeps them now
    books = dict(Book.objects.values_list('name', 'sha'))
    assert all(books.get(name) == sha for name, sha in LAB_BOOKS.items()), 'a book of the lab is missing or changed'
    assert Book.objects.filter(name__in=LAB_BOOKS, enabled=True).count() == len(LAB_BOOKS)
    elephant = EngineConfig.objects.get(name='elephant')
    assert elephant.enabled and elephant.nps == 1487000 and elephant.source == 'https://github.com/looak/elephant'
    assert elephant.build_path == 'ob_build' and set(elephant.presets) == {'test_presets', 'tune_presets', 'datagen_presets'}
    assert elephant.presets['test_presets']['default']['book_name'] == '8moves_v3.epd'
    assert Step.objects.count() == steps

    # What the models have, the tables have, as in a fresh database
    assert schema() == FRESH, { table : (set(columns.items()) ^ set(FRESH[table].items()))
                                for table, columns in schema().items() if columns != FRESH.get(table) }
    call_command('makemigrations', '--check', '--dry-run', verbosity=0)

def test_the_fork_at_d9cdb95():
    use_new_database('fork')
    migrate('0008_test_name')
    apps = seed('0008_test_name')

    # A workload and a step, as the fork's worker has made them
    Result, Step = apps.get_model(APP, 'Result'), apps.get_model(APP, 'Step')
    Step.objects.create(result=Result.objects.get(), step='compile', side='dev', state='passed')

    migrate()
    check_applied('0008_test_name', steps=1)

def test_bobbys_database_older_than_the_steps():
    use_new_database('bobby')
    migrate('0006_result_base_nodes_result_base_time_and_more')
    seed('0006_result_base_nodes_result_base_time_and_more')
    migrate()
    check_applied('0006_result_base_nodes_result_base_time_and_more', steps=0)

def test_a_database_older_than_the_models():

    # Only the first migration applied, and a column the models have is missing (0002 puts it back, upstream's 0007
    # takes it out again)
    use_new_database('oldest')
    migrate('0001_initial')
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "OpenBench_test" DROP COLUMN "spsa"')

    migrate()

    from OpenBench.models import Book, EngineConfig
    assert schema() == FRESH
    assert Book.objects.filter(name='8moves_v3.epd').exists() and EngineConfig.objects.filter(name='elephant').exists()

def test_an_elephant_edited_on_the_website_is_left_alone():
    use_new_database('edited')
    migrate('0017_network_ob_compressed')

    from OpenBench.models import EngineConfig
    EngineConfig.objects.create(name='elephant', nps=1234, source='https://example.invalid/elephant', presets={})
    migrate()
    assert EngineConfig.objects.get(name='elephant').nps == 1234

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    FRESH = fresh_schema()
    for test in (test_the_fork_at_d9cdb95, test_bobbys_database_older_than_the_steps,
                 test_a_database_older_than_the_models, test_an_elephant_edited_on_the_website_is_left_alone):
        test()
        print('PASS', test.__name__)
