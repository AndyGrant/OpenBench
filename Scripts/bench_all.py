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
import re
import sys

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(os.path.join(PARENT, 'Client')))

from utils import *
from bench import run_benchmark

def engine_binary_name(engine, configs):
    return '%s-%s' % (engine, configs[engine]['test_presets']['default']['base_branch'])

def delete_engine_binaries(engines, configs):

    for engine in engines:

        name   = engine_binary_name(engine, configs)
        binary = check_for_engine_binary(os.path.join('Engines', name))

        if binary:
            os.remove(binary)

def get_default_network(args, network):

    # Download the default Network
    net_name = network['name']
    net_sha  = network['sha']
    net_path = os.path.join('Networks', net_sha)
    download_network(args.server, args.username, args.password, engine, net_name, net_sha, net_path)

    return net_path

def get_engine(engine, config):

    make_path = config['build']['path']
    branch    = config['test_presets']['default']['base_branch']
    out_path  = os.path.join('Engines', '%s-%s' % (engine, branch))
    target    = url_join(config['source'], 'archive', '%s.zip' % (branch))

    net_sha   = config.get('network', {}).get('sha')
    net_path  = os.path.join('Networks', net_sha) if net_sha else None

    try:
        prepare_engine(engine, net_path, branch, target, make_path, out_path, config['private'])

    except OpenBenchBuildFailedException as error:
        print ('Failed to build %s...\n\nCompiler Output:' % (engine))
        for line in error.logs.split('\n'):
            print ('> %s' % (line))
        print ()

if __name__ == '__main__':

    # Use bench_all.py's path as the base pathway
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Ensure the folder structure for ease of coding
    for folder in ['Engines', 'Networks']:
        if not os.path.isdir(folder):
            os.mkdir(folder)

    # credentialed_cmdline_args() adds --user, --password, and --server
    parser = argparse.ArgumentParser()
    parser.add_argument('--rebuild', help='Forcefully rebuild all engines', action='store_true')
    parser.add_argument('--regex',   help='Regex to match Engine names')
    parser.add_argument('--engines', help='List of specific engines', nargs='+')
    parser.add_argument('--threads', help='Concurrent Benchmarks',  required=True, type=int)
    parser.add_argument('--sets'   , help='Benchmark Sample Count', required=True, type=int)
    args   = credentialed_cmdline_args(parser)

    # Get the build info, and default network info, for all applicable engines
    request = credentialed_request(args.server, args.username, args.password, 'api/buildinfo')
    configs = request.json()

    # Filter down to only engines provided via --engines, if applicable
    engines = configs.keys() if not args.engines else args.engines
    engines = list(set(engines) & set(configs.keys()))

    # Filter down to only engines matching --regex, if applicable
    if args.regex:
        engines = list(filter(lambda x: re.match(args.regex, x), engines))

    # Delete any existing engines that are to be rebuilt
    if args.rebuild:
        delete_engine_binaries(engines, configs)

    # Get all the default Network files for the engines
    for engine in engines:
        if configs[engine].get('network'):
            get_default_network(args, configs[engine]['network'])

    # Download source and build each engine
    for engine in engines:
        get_engine(engine, configs[engine])

    # Pretty Formatting
    max_length   = max(len(engine) for engine in engines)
    print_format = '%-' + str(max_length) + 's %8d nps %10d nodes in %6.3f seconds'

    for engine in engines:

        # Files are saved in Engines/<Engine>-<Branch>
        path = os.path.join('Engines', engine_binary_name(engine, configs))

        # Builds may have failed in previous steps, which we can ignore
        if not (binary := check_for_engine_binary(path)):
            print ('Unable to find binary for %s...' % (engine))
            continue

        try:
            nps, nodes = run_benchmark(binary, args.threads, args.sets)
            print (print_format % (engine, nps, nodes, nodes / max(1e-6, nps)))

        except OpenBenchBadBenchException as error:
            print ('%s: %s' % (engine, error))
