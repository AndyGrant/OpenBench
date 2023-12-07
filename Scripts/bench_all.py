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
import cpuinfo
import os
import requests
import sys

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(PARENT))

from Client.utils import url_join
from Client.utils import credentialed_cmdline_args
from Client.utils import credentialed_request
from Client.utils import read_git_credentials
from Client.utils import download_network
from Client.utils import download_public_engine
from Client.utils import download_private_engine


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

def get_public_engine(engine, config, net_path):

    make_path = config['build']['path']
    branch    = config['test_presets']['default']['base_branch']
    out_path  = os.path.join('Engines', engine)
    target    = url_join(config['source'], 'archive', '%s.zip' % (branch))

    download_public_engine(engine, net_paths[engine], branch, target, make_path, out_path)

def get_private_engine(engine, config):

    out_path = os.path.join('Engines', engine)
    branch   = config['test_presets']['default']['base_branch']

    # Format an API request to get the most recent openbench.yml workflow on the primary branch
    api_repo = config['source'].replace('github.com', 'api.github.com/repos')
    target   = url_join(api_repo, 'actions/workflows/openbench.yml/runs', trailing_slash=False)
    target  += '?branch=%s' % (branch)

    # Use the run_id for the primary branch's openbench.yml workflow to locate the artifacts
    headers  = read_git_credentials(engine)
    run_id   = requests.get(url=target, headers=headers).json()['workflow_runs'][0]['id']
    source   = url_join(api_repo, 'actions/runs/%d/artifacts' % (run_id), trailing_slash=False)

    # Selecting an artifact requires knowledge of the CPU
    cpu_info  = cpuinfo.get_cpu_info()
    cpu_name  = cpu_info.get('brand_raw', cpu_info.get('brand', 'Unknown'))
    cpu_flags = [x.replace('_', '').replace('.', '').upper() for x in cpu_info.get('flags', [])]

    download_private_engine(engine, branch, source, out_path, cpu_name, cpu_flags, None)

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

    configs = {} # Get the configuration file for all the engines
    for engine in request.json()['engines']:
        endpoint = 'api/config/%s' % (engine)
        request  = credentialed_request(args.server, args.username, args.password, endpoint)
        configs[engine] = request.json()

    net_paths = {} # Get all the Network files for the engines
    for engine, config in configs.items():
        endpoint = 'api/networks/%s' % (engine)
        request  = credentialed_request(args.server, args.username, args.password, endpoint)
        net_paths[engine] = get_default_network_if_any(args, request.json())

    # Download, build, and move the Private engines to Engines/<engine>
    for engine, config in configs.items():
        if config['private']:
            get_private_engine(engine, config)

    # Download and move the Public engines to Engines/<engine>
    for engine, config in configs.items():
        if not config['private']:
            get_public_engine(engine, config, net_paths[engine])



