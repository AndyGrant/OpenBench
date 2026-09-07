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

from OpenBench.configuration import ConfigMapping, configuration_checksum

OPENBENCH_STATIC_VERSION = 'v19'
OPENBENCH_CONFIG = ConfigMapping()


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

    valid_keys += ['test_mode', 'dev_repo', 'base_repo', 'base_engine', 'scale_method', 'scale_nps', 'info']

    for key in test_preset.keys():
        if key not in valid_keys:
            raise Exception('Contains invalid key: %s' % (key))
    return valid_keys

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

    valid_keys += ['dev_repo', 'scale_method', 'scale_nps', 'spsa_inputs', 'info']

    for key in tune_preset.keys():
        if key not in valid_keys:
            raise Exception('Contains invalid key: %s' % (key))
    return valid_keys

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

    valid_keys += ['dev_repo', 'base_repo', 'base_engine', 'scale_method', 'scale_nps', 'info']

    for key in datagen_preset.keys():
        if key not in valid_keys:
            raise Exception('Contains invalid key: %s' % (key))
    return valid_keys
