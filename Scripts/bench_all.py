#!/bin/python3

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   OpenBench is a chess engine testing framework by Andrew Grant.          #
#   <https://github.com/AndyGrant/OpenBench>  <andrew@grantnet.us>          #
#                                                                           #
#   OpenBench is free software: you can redistribute it and/or modify       #
#   it under the terms of the GNU General Public License as published by    #
#   the Free Software Foundation, either version 3 of the License, or       #
#   (at your option) any later version.                                     #
#                                                                           #
#   OpenBench is distributed in the hope that it will be useful,            #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of          #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           #
#   GNU General Public License for more details.                            #
#                                                                           #
#   You should have received a copy of the GNU General Public License       #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.   #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import argparse
import os
import requests
import sys

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(PARENT))

from Client.utils import url_join
from Client.utils import credentialed_cmdline_args
from Client.utils import credentialed_request
from Client.utils import download_network
from Client.utils import download_public_engine

def get_default_network_if_any(args, networks):

    # Not all engines use Networks
    if 'default' not in networks:
        return None

    # Download the default Network
    net_name = networks['default']['name']
    net_sha  = networks['default']['sha']
    net_path = os.path.join('Networks', net_sha)
    download_network(args.server, args.username, args.password, engine, net_name, net_sha, net_path)

    return net_path

if __name__ == '__main__':

    # Use bench_all.py's path as the base pathway
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Ensure the folder structure for ease of coding
    for folder in ['Engines', 'Networks']:
        if not os.path.isdir(folder):
            os.mkdir(folder)

    # Get the list of engines on the Server
    args    = credentialed_cmdline_args()
    request = credentialed_request(args.server, args.username, args.password, 'api/config')

    for engine in request.json()['engines']:

        if engine == 'Torch':
            continue

        # Get the configuration file for the engine
        endpoint = 'api/config/%s' % (engine)
        request  = credentialed_request(args.server, args.username, args.password, endpoint)
        config   = request.json()

        # Get the list of all Networks for the engine
        endpoint = 'api/networks/%s' % (engine)
        request  = credentialed_request(args.server, args.username, args.password, endpoint)
        net_path = get_default_network_if_any(args, request.json())

        # Download, build, and move the engine to Engines/<engine>
        make_path = config['build']['path']
        branch    = config['test_presets']['default']['base_branch']
        out_path  = os.path.join('Engines', engine)
        target    = url_join(config['source'], 'archive', '%s.zip' % (branch))
        download_public_engine(engine, net_path, branch, target, make_path, out_path)
