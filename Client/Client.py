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
import hashlib
import json
import multiprocessing
import os
import platform
import psutil
import queue
import re
import requests
import shutil
import sys
import threading
import time
import traceback
import uuid
import zipfile

from subprocess import PIPE, Popen, call, STDOUT
from itertools import combinations_with_replacement
from concurrent.futures import ThreadPoolExecutor

## Basic configuration of the Client. These timeouts can be changed at will

TIMEOUT_HTTP     = 30   # Timeout in seconds for HTTP requests
TIMEOUT_ERROR    = 10   # Timeout in seconds when any errors are thrown
TIMEOUT_WORKLOAD = 30   # Timeout in seconds between workload requests
CLIENT_VERSION   = '12' # Client version to send to the Server

IS_WINDOWS = platform.system() == 'Windows' # Don't touch this
IS_LINUX   = platform.system() != 'Windows' # Don't touch this

class Configuration(object):

    ## Handles configuring the worker with the server. This means collecting
    ## information about the system, as well as holding any of the command line
    ## arguments provided. Lastly, a Configuration() object holds the Workload

    def __init__(self):

        # Basic init of every piece of System specific information
        self.compilers      = {}
        self.git_tokens     = {}
        self.cpu_flags      = []
        self.cpu_name       = ''
        self.os_name        = platform.system()
        self.os_ver         = platform.release()
        self.python_ver     = platform.python_version()
        self.mac_address    = hex(uuid.getnode()).upper()[2:]
        self.logical_cores  = psutil.cpu_count(logical=True)
        self.physical_cores = psutil.cpu_count(logical=False)
        self.ram_total_mb   = psutil.virtual_memory().total // (1024 ** 2)
        self.machine_name   = 'None'
        self.machine_id     = 'None'
        self.secret_token   = 'None'
        self.syzygy_max     = 2

        self.parse_arguments() # Rest of the command line settings
        self.init_client()     # Create folder structure and verify Syzygy
        self.validate_setup()  # Check the threads and sockets values provided

    def parse_arguments(self):

        # We can use ENV variables for the Username and Passwords
        req_user  = required=('OPENBENCH_USERNAME' not in os.environ)
        req_pass  = required=('OPENBENCH_PASSWORD' not in os.environ)
        help_user = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
        help_pass = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'

        # Create and parse all arguments into a raw format
        p = argparse.ArgumentParser()
        p.add_argument('-U', '--username'   , help=help_user           , required=req_user  )
        p.add_argument('-P', '--password'   , help=help_pass           , required=req_pass  )
        p.add_argument('-S', '--server'     , help='Webserver Address' , required=True      )
        p.add_argument('-T', '--threads'    , help='Total Threads'     , required=True      )
        p.add_argument('-N', '--nsockets'   , help='Number of Sockets' , required=True      )
        p.add_argument('-I', '--identity'   , help='Machine pseudonym' , required=False     )
        p.add_argument(      '--syzygy'     , help='Syzygy WDL'        , required=False     )
        p.add_argument(      '--fleet'      , help='Fleet Mode'        , action='store_true')
        p.add_argument(      '--proxy'      , help='Github Proxy'      , action='store_true')
        args = p.parse_args()

        # Extract all of the options
        self.username    = args.username if args.username else os.environ['OPENBENCH_USERNAME']
        self.password    = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
        self.server      = args.server
        self.threads     = int(args.threads)
        self.sockets     = int(args.nsockets)
        self.identity    = args.identity if args.identity else 'None'
        self.syzygy_path = args.syzygy   if args.syzygy   else None
        self.fleet       = args.fleet    if args.fleet    else False
        self.proxy       = args.proxy    if args.proxy    else False

    def init_client(self):

        # Verify that we have make installed
        print('\nLooking for Make... [v%s]' % locate_utility('make'))

        # Use Client.py's path as the base pathway
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

        # Ensure the folder structure for ease of coding
        for folder in ['PGNs', 'Engines', 'Networks', 'Books']:
            if not os.path.isdir(folder):
                os.mkdir(folder)

        # Check until we stop finding valid N-man tables
        if self.syzygy_path:
            while validate_syzygy_exists(self, self.syzygy_max+1):
                self.syzygy_max = self.syzygy_max + 1

        # 1-man and 2-man tables are not a thing
        if self.syzygy_max < 3:
            self.syzygy_max = 0

        # Report highest complete depth that we found
        print('Looking for Syzygy... [%d-Man]' % (self.syzygy_max))

    def validate_setup(self):

        assert self.threads >= self.sockets
        assert self.threads % self.sockets == 0
        assert min(self.threads, self.sockets) >= 1

    def scan_for_compilers(self, data):

        print ('\nScanning for Compilers...')

        # For each engine, attempt to find a valid compiler
        for engine, build_info in data.items():

            # Private engines don't need to be compiled
            if build_info['private']: continue

            # Try to find at least one working compiler
            for compiler in build_info['compilers']:

                # Compilers may require a specific version
                if '>=' in compiler:
                    compiler, version = compiler.split('>=')
                    version = tuple(map(int, version.split('.')))
                else: version = (0, 0, 0)

                # Try to confirm this compiler is present, and new enough
                try:
                    match = get_version(compiler)
                    if tuple(map(int, match.split('.'))) >= version:
                        print('%-16s | %-8s (%s)' % (engine, compiler, match))
                        self.compilers[engine] = (compiler, match)
                        break
                except: continue # Unable to execute compiler

            # Report missing engines in case the User is not expecting it
            if engine not in self.compilers:
                print('%-16s | Missing %s' % (engine, data[engine]['compilers']))

    def scan_for_private_tokens(self, data):

        print ('\nScanning for Private Tokens...')

        # For each engine, attempt to find a valid compiler
        for engine, build_info in data.items():

            # Public engines don't need access tokens
            if not build_info['private']: continue

            # Private engines expect a credentials.engine file for the main repo
            has_token = os.path.exists('credentials.%s' % (engine.replace(' ', '').lower()))
            print('%-16s | %s' % (engine, ['Missing', 'Found'][has_token]))
            if has_token: self.git_tokens[engine] = True

    def scan_for_cpu_flags(self, data):

        print('\nScanning for CPU Flags...')

        # Get all flags, and for sanity uppercase them
        info   = cpuinfo.get_cpu_info()
        actual = [x.upper() for x in info.get('flags', [])]

        # Set the CPU name which has to be done via global
        self.cpu_name = info.get('brand_raw', info.get('brand', 'Unknown'))

        # This should cover virtually all compiler flags that we would care about
        desired  = ['POPCNT', 'BMI2']
        desired += ['SSSE3', 'SSE4_1', 'SSE4_2', 'SSE4A', 'AVX', 'AVX2', 'FMA']
        desired += ['AVX512_VNNI', 'AVX512BW', 'AVX512DQ', 'AVX512F']

        # Add any custom flags from the OpenBench configs, just in case we missed one
        requested = set(sum([info['cpuflags'] for engine, info in data.items()], []))
        for flag in [x for x in requested if x not in desired]: desired.append(flag)
        self.cpu_flags = [x for x in desired if x in actual]

        # Report the results of our search, including any "missing flags
        print ('Found   |', ' '.join(self.cpu_flags))
        print ('Missing |', ' '.join([x for x in desired if x not in actual]))

    def scan_for_machine_id(self):

        if os.path.isfile('machine.txt'):
            with open('machine.txt') as fin:
                self.machine_id = fin.readlines()[0]

    def choose_best_artifact(self, options):

        # Step 1. Filter down to our operating system only
        options = [x for x in options if x.split('-')[1] == self.os_name.lower()]

        # Pick betwen various Vector instruction sets that might apply
        has_ssse3  =                all(x in self.cpu_flags for x in ['SSSE3'])
        has_sse4   = has_ssse3  and all(x in self.cpu_flags for x in ['SSE4_1', 'SSE4_2'])
        has_avx    = has_sse4   and all(x in self.cpu_flags for x in ['AVX'])
        has_avx2   = has_avx    and all(x in self.cpu_flags for x in ['AVX2', 'FMA'])
        has_avx512 = has_avx2   and all(x in self.cpu_flags for x in ['AVX512BW', 'AVX512DQ', 'AVX512F'])
        has_vnni   = has_avx512 and all(x in self.cpu_flags for x in ['AVX512_VNNI'])

        # Filtering system, where we remove everything but the strongest that is available
        selection = [
            (has_vnni  , 'vnni'  ), (has_avx512, 'avx512'), (has_avx2  , 'avx2'  ),
            (has_avx   , 'avx'   ), (has_sse4  , 'sse4'  ), (has_ssse3 , 'ssse3' ),
        ]

        # Step 2. Filter everything but the best Vector instruction set that was available
        for boolean, identifier in selection:
            if boolean and identifier in [x.split('-')[2] for x in options]:
                options = [x for x in options if x.split('-')[2] == identifier]
                break

        # Identify any Ryzen or AMD chip, excluding the 7B12
        ryzen = 'AMD' in self.cpu_name.upper()
        ryzen = 'RYZEN' in self.cpu_name.upper() or ryzen
        ryzen = ryzen and '7B12' not in self.cpu_name.upper()

        # Pick between POPCNT and BMI2/PEXT
        has_popcnt = 'POPCNT' in self.cpu_flags
        has_bmi2   = 'BMI2' in self.cpu_flags and not ryzen

        # Filtering system, where we remove everything but the strongest that is available
        selection = [ (has_bmi2, 'pext'), (has_popcnt, 'popcnt') ]

        # Step 3. Filter everything but the best bitop instruction set that was available
        for boolean, identifier in selection:
            if boolean and identifier in [x.split('-')[3] for x in options]:
                options = [x for x in options if x.split('-')[3] == identifier]
                break

        return options[0]

class ServerReporter(object):

    ## Handles reporting things to the server, which are not intended to send a great
    ## deal of information back. Reports to the server can hit various endpoints, with
    ## differing payloads. Payloads must always include the machine id, and secret token

    @staticmethod
    def report(config, endpoint, payload):
        payload['machine_id'] = config.machine_id
        payload['secret']     = config.secret_token
        target = url_join(config.server, endpoint)
        return requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

    @staticmethod
    def report_nps(config, dev_nps, base_nps):

        payload = {
            'nps'      : (dev_nps + base_nps) // 2,
            'dev_nps'  : int(dev_nps),
            'base_nps' : int(base_nps),
        }

        return ServerReporter.report(config, 'clientSubmitNPS', payload)

    @staticmethod
    def report_missing_artifact(config, artifact_name, artifact_json):

        payload = {
            'test_id'    : config.workload['test']['id'],
            'error'      : 'Artifact %s missing' % (artifact_name),
            'logs'       : json.dumps(artifact_json, indent=2),
        }

        return ServerReporter.report(config, 'clientSubmitError', payload)

    @staticmethod
    def report_build_fail(config, branch, output):

        branch_name = config.workload['test'][branch]['name']
        engine_name = config.workload['test'][branch]['engine']
        final_name  = '[%s] %s' % (engine_name, branch_name)

        payload = {
            'test_id'    : config.workload['test']['id'],
            'error'      : '%s build failed' % (final_name),
            'logs'       : output,
        }

        return ServerReporter.report(config, 'clientSubmitError', payload)

    @staticmethod
    def report_engine_error(config, cutechess_str, pgn):

        white, black = cutechess_str.split('(')[1].split(')')[0].split(' vs ')

        error = cutechess_str.split('{')[1].rstrip().rstrip('}')
        error = error.replace('White', '-'.join(white.split('-')[1:]).rstrip())
        error = error.replace('Black', '-'.join(black.split('-')[1:]).rstrip())

        payload = {
            'test_id'    : config.workload['test']['id'],
            'error'      : error,
            'logs'       : pgn,
        }

        return ServerReporter.report(config, 'clientSubmitError', payload)

    @staticmethod
    def report_bad_bench(config, branch, bench):

        payload = {
            'test_id'    : config.workload['test']['id'],
            'engine'     : config.workload['test'][branch]['name'],
            'correct'    : config.workload['test'][branch]['bench'],
            'wrong'      : bench,
        }

        return ServerReporter.report(config, 'clientWrongBench', payload)

    @staticmethod
    def report_results(config, batches):

        payload = {

            'test_id'     : config.workload['test']['id'],
            'result_id'   : config.workload['result']['id'],

            'trinomial'   : [0, 0, 0],       # LDW
            'pentanomial' : [0, 0, 0, 0, 0], # LL DL DD DW WW

            'crashes'     : 0, # " disconnect" or "connection stalls"
            'timelosses'  : 0, # " loses on time "
            'illegals'    : 0, # " illegal move "
        }

        for batch in batches:

            payload['trinomial'  ] = [x+y for x,y in zip(payload['trinomial'  ], batch['trinomial'  ])]
            payload['pentanomial'] = [x+y for x,y in zip(payload['pentanomial'], batch['pentanomial'])]

            payload['crashes'   ] += batch['crashes'   ]
            payload['timelosses'] += batch['timelosses']
            payload['illegals'  ] += batch['illegals'  ]

        # Collapse into a JSON friendly format for Django
        payload['trinomial'  ] = ' '.join(map(str, payload['trinomial'  ]))
        payload['pentanomial'] = ' '.join(map(str, payload['pentanomial']))

        return ServerReporter.report(config, 'clientSubmitResults', payload)

class Cutechess(object):

    ## Handles building the very long string of arguments that need to be passed
    ## to cutechess in order to launch a set of games. Operates on the Configuration,
    ## and a small number of secondary arguments that are not housed in the Configuration

    @staticmethod
    def basic_settings(config, socket):

        # Book seed, with an offset between concurrent Cutechesses
        seed = time.time() + socket

        # Assume Fischer if FRC, 960, or FISCHER appears in the Opening Book
        book_name = config.workload['test']['book']['name'].upper()
        is_frc    = 'FRC' in book_name or '960' in book_name or 'FISCHER' in book_name
        variant   = ['standard', 'fischerandom'][is_frc]

        # Always include -repeat and -recover
        return '-repeat -recover -srand %d -variant %s' % (seed, variant)

    @staticmethod
    def concurrency_settings(config):

        # Extract # of Threads for the dev engine
        dev_options  = config.workload['test']['dev' ]['options']
        dev_threads  = int(extract_option(dev_options,  'Threads'))

        # Extract # of Threads for the base engine
        base_options = config.workload['test']['base']['options']
        base_threads = int(extract_option(base_options, 'Threads'))

        # Number of concurrency games that this socket can play
        concurrency = config.threads / config.sockets
        concurrency = concurrency // max(dev_threads, base_threads)

        # Play at least a single game-pair per concurrency
        games = int(concurrency * config.workload['test']['workload_size'])
        games = max(concurrency * 2, games - (games % (2 * concurrency)))

        return '-concurrency %d -games %d' % (concurrency, games)

    @staticmethod
    def adjudication_settings(config):

        # All three possible adjudication settings
        win_adj    = config.workload['test']['win_adj'   ]
        draw_adj   = config.workload['test']['draw_adj'  ]
        syzygy_adj = config.workload['test']['syzygy_adj']

        # Empty, unless specified in the settings
        win_flags    = ['', '-resign ' + win_adj ][win_adj  != 'None']
        draw_flags   = ['', '-draw '   + draw_adj][draw_adj != 'None']
        syzygy_flags = ''

        # Set the tb path if we have them, and are allowed to use them
        if syzygy_adj != 'DISABLED' and config.syzygy_max:
            syzygy_flags = '-tb %s' % (config.syzygy_path.replace('\\', '\\\\'))

        # We would only get a test we can do; specify a limit if needed
        if syzygy_adj != 'DISABLED' and syzygy_adj != 'OPTIONAL':
            syzygy_flags += ' -tbpieces %s' % (syzygy_adj.split('-')[0])

        return '%s %s %s' % (win_flags, draw_flags, syzygy_flags)

    @staticmethod
    def book_settings(config):

        # Can handle EPD and PGN Books, which must be specified
        book_name   = config.workload['test']['book']['name']
        book_suffix = book_name.split('.')[-1]
        return '-openings file=Books/%s format=%s order=random plies=16' % (book_name, book_suffix)

    @staticmethod
    def engine_settings(config, command, branch, scale_factor):

        # Extract configuration from the Workload
        options = config.workload['test'][branch]['options']
        network = config.workload['test'][branch]['network']
        private = config.workload['test'][branch]['private']
        syzygy  = config.workload['test']['syzygy_wdl']

        # Human-readable name, and scale the time control
        name    = command.removesuffix('.exe')
        control = scale_time_control(config.workload, scale_factor, branch)

        # Private engines, when using Networks, must set them via UCI
        if private and network and network != 'None':
            options += ' EvalFile=%s' % (os.path.join('../Networks', network))
            name    += '-%s' % (network)

        # Set the SyzygyPath if we have them, and are allowed to use them
        if syzygy != 'DISABLED' and config.syzygy_max:
            options += ' SyzygyPath=%s' % (config.syzygy_path.replace('\\', '\\\\'))

        # Set a SyzygyProbeLimit if we may only use up-to N-Man
        if syzygy != 'DISABLED' and syzygy != 'OPTIONAL':
            options += ' SyzygyProbeLimit=%s' % (syzygy.split('-')[0])

        # Join options together in the Cutechess format
        options = ' option.'.join([''] + re.findall(r'"[^"]*"|\S+', options))
        return '-engine dir=Engines/ cmd=./%s proto=uci %s%s name=%s-%s' % (command, control, options, name, branch)

    @staticmethod
    def pgnout_settings(config, dev_cmd, base_cmd, socket):

        # Extract Network names
        dev_network  = config.workload['test']['dev' ]['network']
        base_network = config.workload['test']['base']['network']

        # Extract private status
        dev_private  = config.workload['test']['dev' ]['private']
        base_private = config.workload['test']['base']['private']

        # Append Network name for private engines
        dev_name = dev_cmd.removesuffix('.exe')
        if dev_private and dev_network and dev_network != 'None':
            dev_name += '-%s' % (dev_network)

        # Append Network name for private engines
        base_name = base_cmd.removesuffix('.exe')
        if base_private and base_network and base_network != 'None':
            base_name += '-%s' % (base_network)

        # Tack the socket number onto the end to distinguish the PGNs
        return '-pgnout PGNs/%s_vs_%s.%d' % (dev_name, base_name, socket)

    @staticmethod
    def update_results(results, line):

        # Given any game #, find the other in the pair
        def game_to_pair(g):
            return (g, g+1) if g % 2 else (g-1, g)

        # Find the Pentanomial index given a game pair
        def pair_to_penta(r1, r2):
            lookup = { '0-1' : 0, '1/2-1/2' : 1, '1-0' : 2 }
            return lookup[r1] + 2 - lookup[r2]

        # Find the Trinomial indices, from our POV, for a give game pair
        def pair_to_trinomial(r1, r2):
            lookup = { '0-1' : 0, '1/2-1/2' : 1, '1-0' : 2 }
            return lookup[r1], 2 - lookup[r2]

        # Extract the game # and result str from a Cutechess line
        def parse_finished_game(line):
            tokens = line.split()
            return int(tokens[2]), tokens[6]

        # Parse for errors resulting in adjudication
        reason = line.split(':')[1]
        results['crashes'   ] += 'disconnect' in reason or 'stalls' in reason
        results['timelosses'] += 'on time' in reason
        results['illegals'  ] += 'illegal' in reason

        # Parse Game # and result, and save
        game, result = parse_finished_game(line)
        results['games'][game] = result

        # Check to see if the Pair has finished
        first, second = game_to_pair(game)
        if first not in results['games'] or second not in results['games']:
            return

        # Get the indices for the Pentanomial, and the two for Trinomial
        p = pair_to_penta(results['games'][first], results['games'][second])
        t1, t2 = pair_to_trinomial(results['games'][first], results['games'][second])

        # Update everything
        results['trinomial'  ][t1] += 1
        results['trinomial'  ][t2] += 1
        results['pentanomial'][p ] += 1

        # Clean up results['games']
        del results['games'][first]
        del results['games'][second]

class ResultsReporter(object):

    def __init__(self, config, tasks, results_queue, abort_flag):
        self.config        = config
        self.tasks         = tasks
        self.results_queue = results_queue
        self.abort_flag    = abort_flag

    def process_until_finished(self):

        self.last_report = 0
        self.pending     = []

        # Collect results until all Tasks are done
        while any(not task.done() for task in self.tasks):

            if (result := self.get_next_result()):
                self.pending.append(result)

            # Send results every 30 seconds, until all Tasks are done
            if self.send_results(report_interval=30):
                return

            # Kill everything if openbench.exit is created
            if os.path.isfile('openbench.exit'):
                return self.abort_flag.set()

        # Exhaust the Results Queue completely since Tasks are done
        while (result := self.get_next_result()):
            self.pending.append(result)

        # Send any remaining results immediately
        self.send_results(report_interval=0)

    def get_next_result(self):
        try: return self.results_queue.get(timeout=5)
        except queue.Empty: return None

    def send_results(self, report_interval):

        # Nothing to send, or we are sending too frequently
        if not self.pending or self.last_report + report_interval > time.time():
            return False

        # Most recent time we sent a report is now
        self.last_report = time.time()

        try:
            # Send all of the queued Results at once
            response = ServerReporter.report_results(self.config, self.pending)

            # Log, and then clear pending queue
            for result in self.pending:
                print (result)
            self.pending = []

            # If the test ended, kill all tasks
            if 'stop' in response.json():
                self.abort_flag.set()

            # Signal an exit if the test ended
            return 'stop' in response.json()

        except Exception:
            traceback.print_exc()
            print ('[Note] Failed to upload results to server...')


def get_version(program):

    # Try to execute the program from the command line
    # First with `--version`, and again with just `version`

    try:
        process = Popen([program, '--version'], stdout=PIPE, stderr=PIPE)
        stdout  = process.communicate()[0].decode('utf-8')
        return re.search(r'\d+\.\d+(\.\d+)?', stdout).group()

    except:
        process = Popen([program, 'version'], stdout=PIPE, stderr=PIPE)
        stdout  = process.communicate()[0].decode('utf-8')
        return re.search(r'\d+\.\d+(\.\d+)?', stdout).group()

def locate_utility(util, force_exit=True, report_error=True):

    try: return get_version(util)

    except Exception:
        if report_error: print('[Error] Unable to locate %s' % (util))
        if force_exit: sys.exit()


def cleanup_client():

    SECONDS_PER_DAY   = 60 * 60 * 24
    SECONDS_PER_WEEK  = SECONDS_PER_DAY * 7
    SECONDS_PER_MONTH = SECONDS_PER_WEEK * 4

    file_age = lambda x: time.time() - os.path.getmtime(x)

    for file in os.listdir('PGNs'):
        if file_age(os.path.join('PGNs', file)) > SECONDS_PER_DAY:
            os.remove(os.path.join('PGNs', file))

    for file in os.listdir('Engines'):
        if file_age(os.path.join('Engines', file)) > SECONDS_PER_WEEK:
            os.remove(os.path.join('Engines', file))

    for file in os.listdir('Networks'):
        if file_age(os.path.join('Networks', file)) > SECONDS_PER_MONTH:
            os.remove(os.path.join('Networks', file))

def validate_syzygy_exists(config, K):

    letters = ['', 'Q', 'R', 'B', 'N', 'P']

    # Generate many potential K[] v K[], including all valid ones
    candidates = ['K%svK%s' % (''.join(lhs), ''.join(rhs))
        for N in range(1, K - 1)
            for lhs in combinations_with_replacement(letters, N)
                for rhs in combinations_with_replacement(letters, K - N - 2)]

    # Syzygy does LHS having more pieces first, stronger pieces second
    def valid_filename(name):
        for i, letter in enumerate(letters[1:]):
            name = name.replace(letter, str(9 - i))
        lhs, rhs = name.replace('K', '9').split('v')
        return int(lhs) >= int(rhs) and name != 'KvK'

    # See if file exists in (any of) the paths
    def has_filename(paths, name):
        for path in paths:
            if os.path.isfile(os.path.join(path, name + '.rtbw')):
                return True
        return False

    # Split paths, using ":" on Unix, and ";" on Windows
    paths = config.syzygy_path.split(':' if IS_LINUX else ';')

    # Check to see if each Syzygy File exists as desired
    for filename in list(filter(valid_filename, set(candidates))):
        if not has_filename(paths, filename):
            return False

    return True

def try_forever(func, args, message):

    while True:
        try:
            return func(*args)

        except Exception as exception:
            print ('\n\n' + message)
            print ('[Note] Sleeping for %d seconds' % (TIMEOUT_ERROR))
            print ('[Note] Traceback:')
            traceback.print_exc()
            print ()

        time.sleep(TIMEOUT_ERROR)


def url_join(*args):

    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + '/'

def download_file(source, outname, post_data=None, headers=None):

    arguments = { 'stream' : True, 'timeout' : TIMEOUT_ERROR, 'headers' : headers }
    function  = [requests.get, requests.post][post_data != None]
    if post_data: arguments['data'] = post_data

    request = function(source, **arguments)
    with open(outname, 'wb') as fout:
        for chunk in request.iter_content(chunk_size=1024):
            if chunk: fout.write(chunk)
        fout.flush()

def unzip_delete_file(source, outdir):
    with zipfile.ZipFile(source) as fin:
        fin.extractall(outdir)
    os.remove(source)


def extract_option(options, option):

    match = re.search('(?<={0}=")[^"]*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=\')[^\']*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=)[^ ]*'.format(option), options)
    if match: return match.group()

def make_command(config, engine, src_path, network_path):

    compiler  = config.compilers[engine][0]
    comp_flag = ['CC', 'CXX']['++' in compiler]
    command   = 'make %s=%s EXE=%s -j%d' % (comp_flag, compiler, engine, config.threads)

    if network_path != None:
        path     = os.path.relpath(os.path.abspath(network_path), src_path)
        command += ' EVALFILE=%s' % (path.replace('\\', '/'))

    return command.split()

def parse_bench_output(stream):

    nps = bench = None # Search through output Stream
    for line in stream.decode('ascii').strip().split('\n')[::-1]:

        # Convert non alpha-numerics to spaces
        line = re.sub(r'[^a-zA-Z0-9 ]+', ' ', line)

        # Multiple methods, including Ethereal and Stockfish
        nps_pattern   = r'(\d+\s+nps)|(nps\s+\d+)|(nodes second\s+\d+)'
        bench_pattern = r'(\d+\s+nodes)|(nodes\s+\d+)|(nodes searched\s+\d+)'

        # Search for and set only once the NPS value
        if (re_nps := re.search(nps_pattern, line, re.IGNORECASE)):
            nps = nps if nps else re_nps.group()

        # Search for and set only once the Bench value
        if (re_bench := re.search(bench_pattern, line, re.IGNORECASE)):
            bench = bench if bench else re_bench.group()

    # Parse out the integer portion from our matches
    nps   = int(re.search(r'\d+', nps  ).group()) if nps   else None
    bench = int(re.search(r'\d+', bench).group()) if bench else None

    return (bench, nps)

def run_bench(engine, outqueue, private_net=None):

    try:
        # We may need to set an EvalFile via the UCI Options
        if not private_net: cmd = ['./' + engine, 'bench']
        else: cmd = ['./' + engine, 'setoption name EvalFile value %s' % (private_net), 'bench', 'quit']

        # Launch the engine and parse output for statistics
        stdout, stderr = Popen(cmd, stdout=PIPE, stderr=STDOUT).communicate()
        outqueue.put(parse_bench_output(stdout))
    except Exception: outqueue.put((0, 0))

def scale_time_control(workload, scale_factor, branch):

    # Extract everything from the workload dictionary
    reference_nps = workload['test'][branch]['nps']
    time_control  = workload['test'][branch]['time_control']

    # Searching for Nodes or Depth time controls ("N=", "D=")
    pattern = '(?P<mode>((N))|(D))=(?P<value>(\d+))'
    results = re.search(pattern, time_control.upper())

    # No scaling is needed for fixed nodes or fixed depth games
    if results:
        mode, value = results.group('mode', 'value')
        return 'tc=inf %s=%s' % ({'N' : 'nodes', 'D' : 'depth'}[mode], value)

    # Searching for MoveTime or Fixed Time Controls ("MT=")
    pattern = '(?P<mode>(MT))=(?P<value>(\d+))'
    results = re.search(pattern, time_control.upper())

    # Scale the time based on this machine's NPS. Add a time Margin to avoid time losses.
    if results:
        mode, value = results.group('mode', 'value')
        return 'st=%.2f timemargin=100' % ((float(value) * scale_factor / 1000))

    # Searching for "X/Y+Z" time controls
    pattern = '(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
    results = re.search(pattern, time_control)
    moves, base, inc = results.group('moves', 'base', 'inc')

    # Strip the trailing and leading symbols
    moves = None if moves == '' else moves.rstrip('/')
    inc   = 0.0  if inc   is None else inc.lstrip('+')

    # Scale the time based on this machine's NPS
    base = float(base) * scale_factor
    inc  = float(inc ) * scale_factor

    # Format the time control for cutechess
    if moves is None: return 'tc=%.2f+%.2f' % (base, inc)
    return 'tc=%d/%.2f+%.2f' % (int(moves), base, inc)

def kill_cutechess(cutechess):

    try:

        if IS_WINDOWS:
            call(['taskkill', '/F', '/T', '/PID', str(cutechess.pid)])

        if IS_LINUX:
            cutechess.kill()

        cutechess.wait()
        cutechess.stdout.close()

    except Exception:
        pass

def find_pgn_error(reason, command):

    pgn_file = command.split('-pgnout ')[1].split()[0]
    with open(pgn_file, 'r') as fin:
        data = fin.readlines()

    reason = reason.split('{')[1]
    for ii in range(len(data) - 1, -1, -1):
        if reason in data[ii]:
            break

    pgn = ""
    while "[Event " not in data[ii]:
        pgn = data[ii] + pgn
        ii = ii - 1
    return data[ii] + pgn


## Functions interacting with the OpenBench server that establish the initial
## connection and then make simple requests to retrieve Workloads as json objects

def server_download_cutechess(config):

    print('\nFetching Cutechess Binary...')

    if IS_WINDOWS and not locate_utility('cutechess-ob.exe', False, False):

        # Fetch the source location if we are missing the binary
        source = requests.get(
            url_join(config.server, 'clientGetFiles'),
            timeout=TIMEOUT_HTTP).json()['location']

        if config.proxy: source = 'https://ghproxy.com/' + source

        # Windows workers simply need a static compile (64-bit)
        download_file(url_join(source, 'cutechess-windows.exe').rstrip('/'), 'cutechess-ob.exe')

        # Verify that we can execute Cutechess
        if not locate_utility('cutechess-ob.exe', False):
            raise Exception

    if IS_LINUX and not locate_utility('./cutechess-ob', False, False):

        # Fetch the source location if we are missing the binary
        source = requests.get(
            url_join(config.server, 'clientGetFiles'),
            timeout=TIMEOUT_HTTP).json()['location']

        if config.proxy: source = 'https://ghproxy.com/' + source

        # Linux workers need a static compile (64-bit) with execute permissions
        download_file(url_join(source, 'cutechess-linux').rstrip('/'), 'cutechess-ob')
        os.system('chmod 777 cutechess-ob')

        # Verify that we can execute Cutechess
        if not locate_utility('./cutechess-ob', False):
            raise Exception

def server_configure_worker(config):

    # Server tells us how to build or obtain binaries
    target = url_join(config.server, 'clientGetBuildInfo')
    data   = requests.get(target, timeout=TIMEOUT_HTTP).json()

    config.scan_for_compilers(data)      # Public engine build tools
    config.scan_for_private_tokens(data) # Private engine access tokens
    config.scan_for_cpu_flags(data)      # For executing binaries
    config.scan_for_machine_id()         # None, or the content of machine.txt

    system_info = {
        'compilers'      : config.compilers,      # Key: Engine, Value: (Compiler, Version)
        'tokens'         : config.git_tokens,     # Key: Engine, Value: True, for tokens we have
        'cpu_flags'      : config.cpu_flags,      # List of CPU flags found in the Client or Server
        'cpu_name'       : config.cpu_name,       # Raw CPU name as per py-cpuinfo
        'os_name'        : config.os_name,        # Should be Windows, Linux, or Darwin
        'os_ver'         : config.os_ver,         # Release version of the OS
        'python_ver'     : config.python_ver,     # Python version running the Client
        'mac_address'    : config.mac_address,    # Used to softly verify the Machine IDs
        'logical_cores'  : config.logical_cores,  # Logical cores, to differentiate hyperthreads
        'physical_cores' : config.physical_cores, # Physical cores, to differentiate hyperthreads
        'ram_total_mb'   : config.ram_total_mb,   # Total RAM on the system, to avoid over assigning
        'machine_id'     : config.machine_id,     # Assigned value, or None. Will be replaced if wrong
        'machine_name'   : config.identity,       # Optional pseudonym for the machine, otherwise None
        'concurrency'    : config.threads,        # Threads to use to play games
        'sockets'        : config.sockets,        # Cutechess copies, usually equal to Socket count
        'syzygy_max'     : config.syzygy_max,     # Whether or not the machine has Syzygy support
        'client_ver'     : CLIENT_VERSION,        # Version of the Client, which the server may reject
    }

    payload = {
        'username'    : config.username,
        'password'    : config.password,
        'system_info' : json.dumps(system_info),
    }

    # Send all of this to the server, and get a Machine Id + Secret Token
    target   = url_join(config.server, 'clientWorkerInfo')
    response = requests.post(target, data=payload, timeout=TIMEOUT_HTTP).json()

    # Delete the machine.txt if we have saved an invalid machine number
    if response.get('error', '').lower() == "bad machine id":
        config.machine_id = 'None'
        os.remove('machine.txt')

    # The 'error' header is included if there was an issue
    if 'error' in response:
        raise Exception('[Error] %s' % (response['error']))

    # Save the machine id, to avoid re-registering every time
    with open('machine.txt', 'w') as fout:
        fout.write(str(response['machine_id']))

    # Store machine_id, and the secret for this session
    config.machine_id   = response['machine_id']
    config.secret_token = response['secret']

def server_request_workload(config):

    print('\nRequesting Workload from Server...')

    payload  = { 'machine_id' : config.machine_id, 'secret' : config.secret_token }
    target   = url_join(config.server, 'clientGetWorkload')
    response = requests.post(target, data=payload, timeout=TIMEOUT_HTTP).json()

    # The 'error' header is included if there was an issue
    if 'error' in response:
        raise Exception('[Error] %s' % (response['error']))

    # Log the start of a new Workload
    if 'workload' in response:
        dev_engine  = response['workload']['test']['dev' ]['engine']
        dev_name    = response['workload']['test']['dev' ]['name'  ]
        base_engine = response['workload']['test']['base']['engine']
        base_name   = response['workload']['test']['base']['name'  ]
        print('Workload [%s] %s vs [%s] %s\n' % (dev_engine, dev_name, base_engine, base_name))

    config.workload = response.get('workload', None)


def complete_workload(config):

    # Download the opening book, throws an exception on corruption
    download_opening_book(config)

    # Download each NNUE file, throws an exception on corruption
    dev_network  = download_network_weights(config, 'dev' )
    base_network = download_network_weights(config, 'base')

    # Build or download each engine, or exit if an error occured
    dev_name  = download_engine(config, 'dev' , dev_network )
    base_name = download_engine(config, 'base', base_network)
    if not dev_name or not base_name: return

    # Run the benchmarks and compute the scaling NPS value
    dev_nps  = run_benchmarks(config, 'dev' , dev_name , dev_network )
    base_nps = run_benchmarks(config, 'base', base_name, base_network)

    # Report NPS to server, or exit if an error occured
    if not dev_nps or not base_nps: return
    ServerReporter.report_nps(config, dev_nps, base_nps)

    # Scale the engines together, using their NPS relative to expected
    dev_factor  = config.workload['test']['dev' ]['nps'] / dev_nps
    base_factor = config.workload['test']['base']['nps'] / base_nps
    avg_factor  = (dev_factor + base_factor) / 2

    print () # Record this information
    print ('Scale Factor Dev  : %.4f' % (dev_factor ))
    print ('Scale Factor Base : %.4f' % (base_factor))
    print ('Scale Factor Avg  : %.4f' % (avg_factor ))

    # Launch and manage all of the Cutechess workers
    with ThreadPoolExecutor(max_workers=config.sockets) as executor:

        results    = multiprocessing.Queue()
        abort_flag = threading.Event()

        tasks = [] # Create each of the Cutechess workers
        for x in range(config.sockets):
            cmd = build_cutechess_command(config, dev_name, base_name, avg_factor, x)
            tasks.append(executor.submit(run_and_parse_cutechess, config, cmd, x, results, abort_flag))

        # Process the Queue until we exit, finish, or are told to stop by the server
        try:
            rr = ResultsReporter(config, tasks, results, abort_flag)
            rr.process_until_finished()

        # Kill everything during an Exception, but print it
        except Exception:
            traceback.print_exc()
            abort_flag.set()
            raise

        # Kill everything during a Keyboard Interrupt
        except KeyboardInterrupt:
            abort_flag.set()
            raise

def download_opening_book(config):

    # Log our attempts to download and verify the book
    book_sha256 = config.workload['test']['book']['sha'   ]
    book_source = config.workload['test']['book']['source']
    book_name   = config.workload['test']['book']['name'  ]
    book_path   = os.path.join('Books', book_name)
    print('Fetching Opening Book [%s]' % (book_name))

    # Download file if we do not already have it
    if not os.path.isfile(book_path):
        if config.proxy: book_source = 'https://ghproxy.com/' + book_source
        download_file(book_source, book_name + '.zip')
        unzip_delete_file(book_name + '.zip', 'Books/')

    # Verify SHAs match with the server
    with open(book_path) as fin:
        content = fin.read().encode('utf-8')
        sha256  = hashlib.sha256(content).hexdigest()
    if book_sha256 != sha256: os.remove(book_path)

    # Log SHAs on every workload
    print('Correct  SHA256 %s' % (book_sha256.upper()))
    print('Download SHA256 %s\n' % (   sha256.upper()))

    # We have to have the correct SHA to continue
    if book_sha256 != sha256:
        raise Exception('Invalid SHA for %s' % (book_name))

def download_network_weights(config, branch):

    # Some tests may not use Neural Networks
    engine_name = config.workload['test'][branch]['engine']
    network_sha = config.workload['test'][branch]['network']
    if not network_sha or network_sha == 'None': return None

    # Log that we are obtaining a Neural Network
    pattern = 'Fetching Neural Network [ %s, %-4s ]'
    print(pattern % (network_sha, branch.upper()))

    # Fetch the Netural Network if we do not already have it
    network_path = os.path.join('Networks', network_sha)
    if not os.path.isfile(network_path):
        target  = url_join(config.server, 'clientGetNetwork')
        payload = { 'username' : config.username, 'password' : config.password }
        download_file(url_join(target, engine_name, network_sha), network_path, payload)

    # Verify the download and delete partial or corrupted ones
    with open(network_path, 'rb') as network:
        sha256 = hashlib.sha256(network.read()).hexdigest()
        sha256 = sha256[:8].upper()
    if network_sha != sha256: os.remove(network_path)

    # We have to have the correct Neural Network to continue
    if network_sha != sha256:
        raise Exception('Invalid SHA for %s' % (network_sha))

    return network_path

def download_engine(arguments, branch, network):

    engine      = config.workload['test'][branch]['engine']
    branch_name = config.workload['test'][branch]['name']
    commit_sha  = config.workload['test'][branch]['sha']
    source      = config.workload['test'][branch]['source']
    private     = config.workload['test'][branch]['private']

    # Naming as Engine-CommitSha[:8]-NetworkSha[:8]
    final_name = '%s-%s' % (engine, commit_sha.upper()[:8])
    if network and not private: final_name += '-%s' % (network[-8:])

    # Check to see if we already have the final binary
    final_path = os.path.join('Engines', final_name)
    if os.path.isfile(final_path): return final_name
    if os.path.isfile(final_path + '.exe'): return final_name + '.exe'

    if private:

        # Get the candidate artifacts that we can pick from
        print ('\nFetching Artifacts for %s' % branch_name)
        with open('credentials.%s' % (engine.replace(' ', '').lower())) as fin:
            auth_headers = { 'Authorization' : 'token %s' % fin.readlines()[0].rstrip() }

        # Pick from available artifacts the name of the best one
        artifacts = requests.get(url=source, headers=auth_headers).json()['artifacts']
        options   = [artifact['name'] for artifact in artifacts]
        best      = config.choose_best_artifact(options)

        # Search for our artifact in the list provided
        artifact_id = None
        for artifact in artifacts:
            if artifact['name'] == best:
                artifact_id = artifact['id']

        # Artifact was missing, workload cannot be completed
        if artifact_id == None:
            ServerReporter.report_missing_artifact(config, branch, best, artifacts)
            return None

        # Download the binary that matches our desired artifact
        print ('Downloading [%s] %s' % (branch_name, best))
        base = source.split('/runs/')[0]
        url  = url_join(base, 'artifacts', str(artifact_id), 'zip').rstrip('/')
        download_file(url, 'artifact.zip', None, auth_headers)

        # Unzip the binary, and place it into a known output name
        unzip_delete_file('artifact.zip', 'tmp/')
        output_name = os.path.join('tmp', engine.replace(' ', '').lower())
        os.rename(os.path.join('tmp', os.listdir('tmp/')[0]), output_name)

        # Binaries don't have execute permissions by default
        if IS_LINUX:
            os.system('chmod 777 %s\n' % (output_name))

    if not private:

        # Download and unzip the source from Github
        download_file(source, '%s.zip' % (engine))
        unzip_delete_file('%s.zip' % (engine), 'tmp/')

        # Parse out paths to find the makefile location
        tokens     = source.split('/')
        unzip_name = '%s-%s' % (tokens[-3], tokens[-1].rstrip('.zip'))
        build_path = config.workload['test'][branch]['build']['path']
        src_path   = os.path.join('tmp', unzip_name, *build_path.split('/'))

        # Build the engine and drop it into src_path
        print('\nBuilding [%s]' % (final_path))
        output_name = os.path.join(src_path, engine)
        command     = make_command(config, engine, src_path, network)
        process     = Popen(command, cwd=src_path, stdout=PIPE, stderr=STDOUT)
        cxx_output  = process.communicate()[0].decode('utf-8')
        print (cxx_output)

    # Move the file to the final location ( Linux )
    if os.path.isfile(output_name):
        os.rename(output_name, final_path)
        shutil.rmtree('tmp')
        return final_name

    # Move the file to the final location ( Windows )
    if os.path.isfile(output_name + '.exe'):
        os.rename(output_name + '.exe', final_path + '.exe')
        shutil.rmtree('tmp')
        return final_name + '.exe'

    # Manual builds should have exited by now
    if not private:
        ServerReporter.report_build_fail(config, branch, cxx_output)
        return None


def run_benchmarks(config, branch, engine, network):

    queue   = multiprocessing.Queue()
    name    = config.workload['test'][branch]['name']
    private = config.workload['test'][branch]['private']
    print('\nRunning %dx Benchmarks for %s' % (config.threads, name))

    args = [os.path.join('Engines', engine), queue]
    if private and network:
        args.append(network)

    # Run the benchmark on all threads we are using
    workers = [
        multiprocessing.Process(target=run_bench, args=args)
        for ii in range(config.threads)
    ]

    # Start and wait for each worker to finish
    for worker in workers: worker.start()
    for worker in workers: worker.join()

    # Collect all bench and nps values, and set bench to 0 if any vary
    bench, nps = list(zip(*[queue.get() for ii in range(config.threads)]))
    bench = [0, bench[0]][len(set(bench)) == 1]
    nps   = sum(nps) // config.threads

    # Output everything, including 0 for an error
    print('Bench for %s is %d' % (name, bench))
    print('Speed for %s is %d' % (name, nps))

    # Flag the test to abort if we have a bench mismatch
    if error := (bench != int(config.workload['test'][branch]['bench'])):
        ServerReporter.report_bad_bench(config, branch, bench)

    # Set NPS to 0 if we had any errors
    return 0 if not bench or error else nps

def build_cutechess_command(config, dev_cmd, base_cmd, scale_factor, socket):

    flags  = ' ' + Cutechess.basic_settings(config, socket)
    flags += ' ' + Cutechess.concurrency_settings(config)
    flags += ' ' + Cutechess.adjudication_settings(config)
    flags += ' ' + Cutechess.engine_settings(config, dev_cmd, 'dev', scale_factor)
    flags += ' ' + Cutechess.engine_settings(config, base_cmd, 'base', scale_factor)
    flags += ' ' + Cutechess.book_settings(config)
    flags += ' ' + Cutechess.pgnout_settings(config, dev_cmd, base_cmd, socket)

    return ['cutechess-ob.exe', './cutechess-ob'][IS_LINUX] + flags

def run_and_parse_cutechess(config, command, socket, results_queue, abort_flag):

    print('\n[#%d] Launching Cutechess...\n%s\n' % (socket, command))
    cutechess = Popen(command.split(), stdout=PIPE)

    results = {

        'trinomial'   : [0, 0, 0],       # LDW
        'pentanomial' : [0, 0, 0, 0, 0], # LL DL DD DW WW
        'games'       : {},              # game_id : result_str

        'crashes'     : 0,               # " disconnect" or "connection stalls"
        'timelosses'  : 0,               # " loses on time "
        'illegals'    : 0,               # " illegal move "
    }

    # Read each line of output until the pipe closes and we get "" back
    while (line := cutechess.stdout.readline().strip().decode('ascii')):

        if abort_flag.is_set():
            return kill_cutechess(cutechess)

        if 'Started game' not in line and 'Score of' not in line:
            print('[#%d] %s' % (socket, line))

        if 'Finished game' in line:
            Cutechess.update_results(results, line)

        # Report results at the end, or once hitting the report_rate
        report = 'Elo difference' in line
        report = report or sum(results['pentanomial']) == config.workload['test']['report_rate']

        if report:

            # Place the results into the Queue, and be sure to copy the lists
            results_queue.put({
                'trinomial'   : list(results['trinomial']),
                'pentanomial' : list(results['pentanomial']),
                'crashes'     : results['crashes'],
                'timelosses'  : results['timelosses'],
                'illegals'    : results['illegals'],
            })

            # Clear out all the results, so we can start collecting a new set
            results['trinomial'  ] = [0, 0, 0]
            results['pentanomial'] = [0, 0, 0, 0, 0]
            results['crashes'    ] = 0
            results['timelosses' ] = 0
            results['illegals'   ] = 0

    cutechess.wait() # Gracefully exit

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#                                                                           #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

if __name__ == '__main__':

    config = Configuration() # System info, Cmdline arguments, and Workload

    cutechess_error  = '[Note] Unable to fetch Cutechess location and download it!'
    setup_error      = '[Note] Unable to establish initial connection with the Server!'
    connection_error = '[Note] Unable to reach the server to request a workload!'

    try_forever(server_download_cutechess, [config], cutechess_error)
    try_forever(server_configure_worker,   [config], setup_error    )

    while True:
        try:
            # Cleanup on each workload request
            cleanup_client()

            # Keep asking for a workload until we get a response
            try_forever(server_request_workload, [config], connection_error)

            # Complete the workload if there was work to be done
            if config.workload: complete_workload(config)

            # Otherwise --fleet workers will exit when there is no work
            elif config.fleet: break

            # In either case, wait before requesting again
            else: time.sleep(TIMEOUT_WORKLOAD)

            # Check for exit signal via openbench.exit
            if os.path.isfile('openbench.exit'):
                print('Exited via openbench.exit')
                break

        except Exception:
            traceback.print_exc()
            time.sleep(TIMEOUT_ERROR)
