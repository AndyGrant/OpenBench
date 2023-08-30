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

import json, os.path, sys
from OpenSite.settings import PROJECT_PATH

def load_json_config(*path):
    try:
        with open(os.path.join(PROJECT_PATH, *path)) as fin:
            return json.load(fin)
    except:
        print ('Error reading ', path)
        sys.exit()

def load_folder_of_configs(*path):
    return {
        fname.removesuffix('.json') : load_json_config(*path, fname)
        for fname in os.listdir(os.path.join(PROJECT_PATH, *path)) if fname.endswith('.json')
    }

USE_CROSS_APPROVAL          = False # Require a second user to approve patches
REQUIRE_LOGIN_TO_VIEW       = True  # Block all content but Login and Regiser by default
REQUIRE_MANUAL_REGISTRATION = False # Disable the public facing registration page

OPENBENCH_CONFIG = {

    # Server Client version control
    'client_version' : '13',

    # Generic Error Messages useful to those setting up their own instance
    'error' : {
        'disabled'            : 'Account has not been enabled. Contact an Administrator',
        'fakeuser'            : 'This is not a real OpenBench User. Create an OpenBench account',
        'requires_login'      : 'All pages require a user login to access',
        'manual_registration' : 'Registration can only be done via an Administrator',
    },

    # Link to the repo on the sidebar, as well as the core files
    'framework' : 'http://github.com/AndyGrant/OpenBench/',
    'corefiles' : 'https://raw.githubusercontent.com/AndyGrant/OpenBench/master/CoreFiles',

    # Test Configuration. For both SPRT and Fixed Games Tests
    'tests' : {
        'max_games'  : '40000',        # Default for Fixed Games
        'confidence' : '[0.10, 0.05]', # SPRT Type I/II Confidence
    },

    # Take a look at Books/books.json
    'books'   : load_json_config('Books', 'books.json'),

    # Take a look at json file in Engines/
    'engines' : load_folder_of_configs('Engines'),
}
