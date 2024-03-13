# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import json
import os
import sys
import traceback

from OpenSite.settings import PROJECT_PATH

OPENBENCH_STATIC_VERSION = 'v3'

OPENBENCH_CONFIG = None # Initialized by OpenBench/apps.py

def create_openbench_config():

    with open(os.path.join(PROJECT_PATH, 'Config', 'config.json')) as fin:
        config_dict = json.load(fin)
        verify_general_config(config_dict)


    config_dict['books'] = {
        book : load_book_config(book) for book in config_dict['books']
    }

    config_dict['engines'] = {
        engine : load_engine_config(engine) for engine in config_dict['engines']
    }

    return config_dict

def load_book_config(book_name):

    with open(os.path.join(PROJECT_PATH, 'Books', '%s.json' % (book_name))) as fin:
        conf = json.load(fin)

    assert type(conf.get('sha')) == str
    assert type(conf.get('source')) == str

    return conf

def load_engine_config(engine_name):

    try:
        with open(os.path.join(PROJECT_PATH, 'Engines', '%s.json' % (engine_name))) as fin:
            conf = json.load(fin)

        verify_engine_basics(conf)
        verify_engine_build(engine_name, conf)

        assert 'default' in conf['test_presets'].keys()
        assert 'default' in conf['tune_presets'].keys()
        assert 'default' in conf['datagen_presets'].keys()

        for key, test_preset in conf['test_presets'].items():
            verify_engine_test_preset(test_preset)

        for key, tune_preset in conf['tune_presets'].items():
            verify_engine_tune_preset(tune_preset)

        for key, datagen_preset in conf['datagen_presets'].items():
          verify_engine_datagen_preset(datagen_preset)

    except Exception as error:
        traceback.print_exc()
        print ('%s has errors on the configuration json' % (engine_name))
        sys.exit()

    return conf


def verify_general_config(conf):

    assert type(conf.get("client_version"  ) == int)
    assert type(conf.get("client_repo_url" ) == str)
    assert type(conf.get("client_repo_ref" ) == str)

    assert type(conf.get("use_cross_approval"         ) == bool)
    assert type(conf.get("require_login_to_view"      ) == bool)
    assert type(conf.get("require_manual_registration") == bool)
    assert type(conf.get("balance_engine_throughputs" ) == bool)

def verify_engine_basics(conf):

    assert type(conf.get('private')) == bool
    assert type(conf.get('nps')) == int and conf['nps'] > 0
    assert type(conf.get('source')) == str
    assert type(conf.get('build')) == dict

def verify_engine_build(engine_name, conf):

    assert type(conf['build'].get('cpuflags')) == list
    assert all(type(x) == str for x in conf['build']['cpuflags'])

    assert type(conf['build'].get('systems')) == list
    assert all(type(x) == str for x in conf['build']['systems'])

    if conf['private']: # Private engines require a PAT
        fname = 'credentials.%s' % (engine_name.replace(' ', '').lower())
        assert os.path.exists(os.path.join(PROJECT_PATH, 'Config', fname))

    else: # Public engines require a Makefile path and valid compilers
        assert type(conf['build'].get('path')) == str
        assert type(conf['build'].get('compilers')) == list
        assert all(type(x) == str for x in conf['build']['compilers'])

def verify_engine_test_preset(test_preset):

    valid_keys = [

        'both_branch',
        'both_bench',
        'both_network',
        'both_options',
        'both_time_control',

        'dev_branch',
        'dev_bench',
        'dev_network',
        'dev_options',
        'dev_time_control',

        'base_branch',
        'base_bench',
        'base_network',
        'base_options',
        'base_time_control',

        'test_bounds',
        'test_confidence',
        'test_max_games',

        'book_name',
        'upload_pgns',
        'priority',
        'throughput',
        'workload_size',
        'syzygy_wdl',

        'syzygy_adj',
        'win_adj',
        'draw_adj',
    ]

    for key in test_preset.keys():
        if key not in valid_keys:
            raise Exception('Contains invalid key: %s' % (key))

def verify_engine_tune_preset(tune_preset):

    valid_keys = [

        'dev_branch',
        'dev_bench',
        'dev_network',
        'dev_options',
        'dev_time_control',

        'spsa_reporting_type',
        'spsa_distribution_type',
        'spsa_alpha',
        'spsa_gamma',
        'spsa_A_ratio',
        'spsa_iterations',
        'spsa_pairs_per',

        'book_name',
        'upload_pgns',
        'priority',
        'throughput',
        'syzygy_wdl',

        'syzygy_adj',
        'win_adj',
        'draw_adj',
    ]

    for key in tune_preset.keys():
        if key not in valid_keys:
            raise Exception('Contains invalid key: %s' % (key))

def verify_engine_datagen_preset(datagen_preset):

    valid_keys = [

        'both_branch',
        'both_bench',
        'both_network',
        'both_options',
        'both_time_control',

        'dev_branch',
        'dev_bench',
        'dev_network',
        'dev_options',
        'dev_time_control',

        'base_branch',
        'base_bench',
        'base_network',
        'base_options',
        'base_time_control',

        'book_name',
        'upload_pgns',
        'priority',
        'throughput',
        'workload_size',
        'syzygy_wdl',

        'syzygy_adj',
        'win_adj',
        'draw_adj',

        'datagen_custom_genfens',
        'datagen_play_reverses',
        'datagen_max_games',
    ]

    for key in datagen_preset.keys():
        if key not in valid_keys:
            raise Exception('Contains invalid key: %s' % (key))