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

OPENBENCH_CONFIG = None # Initialized by OpenBench/apps.py

def create_openbench_config():

    with open(os.path.join(PROJECT_PATH, 'Config', 'config.json')) as fin:
        config_dict = json.load(fin)

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

    with open(os.path.join(PROJECT_PATH, 'Engines', '%s.json' % (engine_name))) as fin:
        conf = json.load(fin)

    verify_engine_basics(engine_name, conf)
    verify_engine_build(engine_name, conf)

    # for test_mode in conf['test_modes']:
    #     verify_engine_test_mode(test_mode)
    #
    # for tune_mode in conf['tune_modes']:
    #     verify_engine_test_mode(test_mode)

    return conf

def verify_engine_basics(engine_name, conf):

    assert type(conf.get('private')) == bool
    assert type(conf.get('nps')) == int and conf['nps'] > 0
    assert type(conf.get('base')) == str
    assert type(conf.get('source')) == str

    assert type(conf.get('bounds')) == str
    assert type(conf.get('book')) == str
    assert type(conf.get('win_adj')) == str
    assert type(conf.get('draw_adj')) == str

    assert type(conf.get('build')) == dict

    assert type(conf.get('test_modes')) == dict
    assert type(conf['test_modes'].get('STC')) == dict

    assert type(conf.get('tune_modes')) == dict
    assert type(conf['tune_modes'].get('STC')) == dict

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