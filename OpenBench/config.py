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

from OpenSite.settings import PROJECT_PATH

OPENBENCH_STATIC_VERSION = 'v18'

OPENBENCH_CONFIG = None # Initialized by OpenBench/apps.py

PRESET_TYPES = [ 'test_presets', 'tune_presets', 'datagen_presets' ]

def create_openbench_config():

    with open(os.path.join(PROJECT_PATH, 'Config', 'config.json')) as fin:
        config_dict = json.load(fin)
        verify_general_config(config_dict)

    return config_dict

def verify_engine_presets(presets):

    # Schema for an EngineConfig.presets JSONField. Returns an error message,
    # or None. Every preset type is required, each with a "default" preset,
    # and each preset may only contain the keys its type knows how to apply.

    verifiers = {
        'test_presets'    : verify_engine_test_preset,
        'tune_presets'    : verify_engine_tune_preset,
        'datagen_presets' : verify_engine_datagen_preset,
    }

    if type(presets) != dict:
        return 'Presets must be a json object'

    if sorted(presets.keys()) != sorted(PRESET_TYPES):
        return 'Presets must contain exactly: %s' % (', '.join(PRESET_TYPES))

    for preset_type, group in presets.items():

        if type(group) != dict or 'default' not in group.keys():
            return '%s must be a json object, containing a "default"' % (preset_type)

        for name, preset in group.items():

            if type(preset) != dict:
                return '%s "%s" must be a json object' % (preset_type, name)

            try: verifiers[preset_type](preset)
            except Exception as error:
                return '%s "%s" %s' % (preset_type, name, error)

    return None


def verify_general_config(conf):

    assert type(conf.get('client_version'  ) == int)
    assert type(conf.get('client_repo_url' ) == str)
    assert type(conf.get('client_repo_ref' ) == str)

    assert type(conf.get('fastchess_min_version') == str)
    assert type(conf.get('fastchess_repo_url') == str)
    assert type(conf.get('fastchess_repo_ref') == str)

    assert type(conf.get('use_cross_approval'         ) == bool)
    assert type(conf.get('require_login_to_view'      ) == bool)
    assert type(conf.get('require_manual_registration') == bool)
    assert type(conf.get('balance_engine_throughputs' ) == bool)

    # Serving of Networks and PGNs may be handed off to an nginx reverse proxy.
    # The root must match an "internal" nginx location, aliased to Media/. ie:
    #     location /x-accel-media/ { internal; alias /path/to/OpenBench/Media/; }

    assert type(conf.get('use_x_accel_redirect' )) == bool
    assert type(conf.get('x_accel_redirect_root')) == str
    assert conf['x_accel_redirect_root'].startswith('/')

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
