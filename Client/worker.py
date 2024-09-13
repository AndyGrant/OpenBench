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
import json
import multiprocessing
import os
import platform
import psutil
import queue
import re
import requests
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile

from subprocess import PIPE, Popen, call, STDOUT
from itertools import combinations_with_replacement
from concurrent.futures import ThreadPoolExecutor

## Local imports

import bench

from client import BadVersionException
from client import url_join
from client import try_forever

from utils import *
from pgn_util import compress_list_of_pgns
from genfens import create_genfens_opening_book

## Basic configuration of the Client. These timeouts can be changed at will

CLIENT_VERSION   = 30 # Client version to send to the Server
TIMEOUT_HTTP     = 30 # Timeout in seconds for HTTP requests
TIMEOUT_ERROR    = 10 # Timeout in seconds when any errors are thrown
TIMEOUT_WORKLOAD = 30 # Timeout in seconds between workload requests
REPORT_INTERVAL  = 30 # Seconds between reports to the Server

IS_WINDOWS = platform.system() == 'Windows' # Don't touch this
IS_LINUX   = platform.system() != 'Windows' # Don't touch this


class Configuration:

    ## Handles configuring the worker with the server. This means collecting
    ## information about the system, as well as holding any of the command line
    ## arguments provided. Lastly, a Configuration() object holds the Workload

    def __init__(self, args):

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
        self.blacklist      = []

        self.process_args(args) # Rest of the command line settings
        self.init_client()      # Create folder structure and verify Syzygy
        self.validate_setup()   # Check the threads and sockets values provided

    def process_args(self, args):

        # Extract all of the options
        self.username    = args.username
        self.password    = args.password
        self.server      = args.server
        self.threads     = int(args.threads)
        self.sockets     = int(args.nsockets)
        self.identity    = args.identity if args.identity else 'None'
        self.syzygy_path = args.syzygy   if args.syzygy   else None
        self.fleet       = args.fleet    if args.fleet    else False
        self.focus       = args.focus    if args.focus    else []

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
        actual = [x.replace("_", "").replace(".", "").upper() for x in info.get('flags', [])]

        # Set the CPU name which has to be done via global
        self.cpu_name = info.get('brand_raw', info.get('brand', 'Unknown'))

        # This should cover virtually all compiler flags that we would care about
        desired  = ['POPCNT', 'BMI2']
        desired += ['SSSE3', 'SSE41', 'SSE42', 'SSE4A', 'AVX', 'AVX2', 'FMA']
        desired += ['AVX512VNNI', 'AVX512BW', 'AVX512DQ', 'AVX512F']

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
                for line in fin.readlines():
                    self.machine_id = line.rstrip(); break

class ServerReporter:

    ## Handles reporting things to the server, which are not intended to send a great
    ## deal of information back. Reports to the server can hit various endpoints, with
    ## differing payloads. Payloads must always include the machine id, and secret token

    @staticmethod
    def report(config, endpoint, payload, files=None):

        payload['machine_id'] = config.machine_id
        payload['secret']     = config.secret_token

        target   = url_join(config.server, endpoint)
        response = requests.post(target, data=payload, files=files, timeout=TIMEOUT_HTTP)

        # Check for a json repsone, to look for Client Version Errors
        try: as_json = response.json()
        except: return response

        # Throw all the way back to the client.py
        if 'Bad Client Version' in as_json.get('error', ''):
            raise BadVersionException()

        return response

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
    def report_engine_error(config, error, pgn=None):

        payload = {
            'test_id'    : config.workload['test']['id'],
            'error'      : error,
            'logs'       : pgn,
        }

        return ServerReporter.report(config, 'clientSubmitError', payload)

    @staticmethod
    def report_bad_bench(config, error):

        payload = {
            'test_id'    : config.workload['test']['id'],
            'error'      : error,
        }

        return ServerReporter.report(config, 'clientBenchError', payload)

    @staticmethod
    def report_results(config, batches):

        payload = {

            'test_id'      : config.workload['test']['id'],
            'result_id'    : config.workload['result']['id'],

            'trinomial'    : [0, 0, 0],       # LDW
            'pentanomial'  : [0, 0, 0, 0, 0], # LL DL DD DW WW

            'crashes'      : 0, # " disconnect" or "connection stalls"
            'timelosses'   : 0, # " loses on time "
            'illegals'     : 0, # " illegal move "
        }

        for batch in batches:

            payload['trinomial'  ] = [x+y for x,y in zip(payload['trinomial'  ], batch['trinomial'  ])]
            payload['pentanomial'] = [x+y for x,y in zip(payload['pentanomial'], batch['pentanomial'])]

            payload['crashes'   ] += batch['crashes'   ]
            payload['timelosses'] += batch['timelosses']
            payload['illegals'  ] += batch['illegals'  ]

            if config.workload['test']['type'] == 'SPSA':

                # Pairs can be added one at a time, or in bulk
                result = batch['trinomial'][2] - batch['trinomial'][0]

                # For each param compute the update step for the Server
                for name, param in config.workload['spsa'].items():
                    delta = param['r'] * param['c'] * result * param['flip'][batch['cutechess_idx']]
                    payload['spsa_%s' % (name)] = payload.get('spsa_%s' % (name), 0.0) + delta

        # Collapse into a JSON friendly format for Django
        payload['trinomial'  ] = ' '.join(map(str, payload['trinomial'  ]))
        payload['pentanomial'] = ' '.join(map(str, payload['pentanomial']))

        print (payload)

        return ServerReporter.report(config, 'clientSubmitResults', payload)

    @staticmethod
    def report_heartbeat(config):

        payload = {
            'test_id' : config.workload['test']['id']
        }

        return ServerReporter.report(config, 'clientHeartbeat', payload)

    @staticmethod
    def report_pgn(config, compressed_pgn_text):

        payload = {
            'test_id'      : config.workload['test']['id'],
            'result_id'    : config.workload['result']['id'],
            'book_index'   : config.workload['test']['book_index'],
            'Content-Type' : 'application/octet-stream',
        }

        files = {
            'file' : ('games.pgn', compressed_pgn_text)
        }

        return ServerReporter.report(config, 'clientSubmitPGN', payload, files)

class Cutechess:

    ## Handles building the very long string of arguments that need to be passed
    ## to cutechess in order to launch a set of games. Operates on the Configuration,
    ## and a small number of secondary arguments that are not housed in the Configuration

    @staticmethod
    def basic_settings(config):

        # Assume Fischer if FRC, 960, or FISCHER appears in the Opening Book
        book_name = config.workload['test']['book']['name'].upper()
        is_frc    = 'FRC' in book_name or '960' in book_name or 'FISCHER' in book_name
        variant   = ['standard', 'fischerandom'][is_frc]

        # Only include -repeat if not skipping the reverses in DATAGEN
        is_datagen = config.workload['test']['type'] == 'DATAGEN'
        no_reverse = is_datagen and not config.workload['test']['play_reverses']

        # Always include -recover and -variant
        return ['-repeat', ''][no_reverse] + ' -recover -variant %s' % (variant)

    @staticmethod
    def concurrency_settings(config):

        # Already computed for us by the Server
        return '-concurrency %d -games %d' % (
            config.workload['distribution']['concurrency-per'],
            config.workload['distribution']['games-per-cutechess'],
        )

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
    def book_settings(config, cutechess_idx):

        # DATAGEN creates their own book
        if config.workload['test']['type'] == 'DATAGEN':

            # -repeat might not be applied, so handle the book offsets
            no_reverse = not config.workload['test']['play_reverses']
            pairs      = config.workload['distribution']['games-per-cutechess'] // 2
            start      = 1 + (cutechess_idx * pairs * (1 + no_reverse))
            return '-openings file=Books/openbench.genfens.epd format=epd order=sequential start=%d' % (start)

        # Can handle EPD and PGN Books, which must be specified
        book_name   = config.workload['test']['book']['name']
        book_suffix = book_name.split('.')[-1]

        # Start position is determined partially by cutechess index
        pairs = config.workload['distribution']['games-per-cutechess'] // 2
        start = config.workload['test']['book_index'] + cutechess_idx * pairs

        return '-openings file=Books/%s format=%s order=random start=%d -srand %d' % (
            book_name, book_suffix, start, config.workload['test']['book_seed'])

    @staticmethod
    def engine_settings(config, command, branch, scale_factor, cutechess_idx):

        # Extract configuration from the Workload
        options = config.workload['test'][branch]['options']
        network = config.workload['test'][branch]['network']
        private = config.workload['test'][branch]['private']
        engine  = config.workload['test'][branch]['engine']
        syzygy  = config.workload['test']['syzygy_wdl']

        # Human-readable name, and scale the time control
        name    = command.replace('.exe', '')
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

        # Add any of the custom SPSA settings
        if config.workload['test']['type'] == 'SPSA':
            for param, data in config.workload['spsa'].items():
                options += ' %s=%s' % (param, str(data[branch][cutechess_idx]))

        # Join options together in the Cutechess format
        options = ' option.'.join([''] + re.findall(r'"[^"]*"|\S+', options))
        return '-engine dir=Engines/ cmd=./%s proto=uci %s%s name=%s-%s' % (command, control, options, engine, branch)

    @staticmethod
    def pgnout_settings(config, timestamp, cutechess_idx):
        return '-pgnout %s' % (Cutechess.pgn_name(config, timestamp, cutechess_idx))

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

    @staticmethod
    def kill_everything(dev_process, base_process):

        if IS_LINUX:
            kill_process_by_name('cutechess-ob')

        if IS_WINDOWS:
            kill_process_by_name('cutechess-ob.exe')

        kill_process_by_name(dev_process)
        kill_process_by_name(base_process)

    @staticmethod
    def pgn_name(config, timestamp, cutechess_idx):

        test_id   = int(config.workload['test']['id'])
        result_id = int(config.workload['result']['id'])

        # Format: <Test>-<Result>-<Time>-<Index>.pgn
        return 'PGNs/%d.%d.%d.%d.pgn' % (test_id, result_id, timestamp, cutechess_idx)


class PGNHelper:

    @staticmethod
    def slice_pgn_file(file):

        with open(file) as pgn:

            while True:

                headers = list(iter(lambda: pgn.readline().rstrip(), ''))
                moves   = list(iter(lambda: pgn.readline().rstrip(), ''))

                if not headers or not moves:
                    break

                yield (headers, moves)

    @staticmethod
    def get_pgn_header(sliced_headers, header):
        for line in sliced_headers:
            if line.startswith('[%s ' % header):
                return line.split('"')[1]

    @staticmethod
    def get_error_reason(sliced_headers):

        reason = PGNHelper.get_pgn_header(sliced_headers, 'Termination')

        if reason and 'abandoned' in reason:
            return 'Disconnect'

        if reason and 'stalled' in reason:
            return 'Stalled'

        if reason and 'illegal' in reason:
            return 'Illegal Move'

    @staticmethod
    def pretty_format(headers, moves):
        return '\n'.join(headers + [''] + moves)

class ResultsReporter(object):

    ## Handles idle looping while reading from the results Queue that the Cutechess
    ## workers place results into. Once finished, this class can be used to collect
    ## all of the errors in the PGN, and send htem back to the server.

    def __init__(self, config, tasks, results_queue, abort_flag):
        self.config        = config
        self.tasks         = tasks
        self.results_queue = results_queue
        self.abort_flag    = abort_flag

    def process_until_finished(self):

        self.last_report = 0
        self.pending     = []

        # Don't report until finished, for BULK SPSA tests
        self.bulk = self.config.workload['test']['type'] == 'SPSA'
        self.bulk = self.bulk and self.config.workload['reporting_type'] == 'BULK'

        # Block up-to 5 seconds to get a new result
        def get_next_result():
            try: return self.results_queue.get(timeout=5)
            except queue.Empty: return False

        # Collect results until all Tasks are done
        while any(not task.done() for task in self.tasks):

            result = get_next_result()
            if result:
                self.pending.append(result)

            # Send results, or a heartbeat, every REPORT_INTERVAL seconds until done
            if self.send_results(report_interval=REPORT_INTERVAL):
                return

            # Kill everything if openbench.exit is created
            if os.path.isfile('openbench.exit'):
                return self.abort_flag.set()

        # Exhaust the Results Queue completely since Tasks are done
        while True:
            result = get_next_result()
            if result:
                self.pending.append(result)
            else:
                break

        # Send any remaining results immediately
        self.send_results(report_interval=0, final_report=True)

    def send_results(self, report_interval, final_report=False):

        # Do not send more often than report_interval dictates
        if self.last_report + report_interval > time.time():
            return False

        try:

            # Heartbeat when no results, or still awaiting bulk results
            if not self.pending or (self.bulk and not final_report):
                response = ServerReporter.report_heartbeat(self.config).json()
                self.last_report = time.time()

            else: # Send all of the queued Results at once
                response = ServerReporter.report_results(self.config, self.pending).json()
                self.last_report = time.time()
                self.pending = []

            # If the test ended, kill all tasks
            if 'stop' in response:
                self.abort_flag.set()

            # Signal an exit if the test ended
            return 'stop' in response

        except BadVersionException:
            self.abort_flag.set()
            return True

        except Exception:
            traceback.print_exc()
            print ('[Note] Failed to upload results to server...')
            self.last_report = time.time()

    def send_errors(self, timestamp, cutechess_cnt):

        for x in range(cutechess_cnt):

            # Reuse logic that was given to Cutechess to decide the PGN name
            fname = Cutechess.pgn_name(self.config, timestamp, x)

            # For any game with weird Termination, report it
            for header, moves in PGNHelper.slice_pgn_file(fname):
                error = PGNHelper.get_error_reason(header)
                if error:
                    as_str = PGNHelper.pretty_format(header, moves)
                    ServerReporter.report_engine_error(self.config, error, as_str)


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

def set_cutechess_permissions():

    status = os.system('sudo -n chmod 777 cutechess-ob > /dev/null 2>&1')

    if status != 0:
        status = os.system('chmod 777 cutechess-ob > /dev/null 2>&1')

    if status != 0:
        print ('[ERROR] Unable to set execute permissions on cutechess-ob')


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


def scale_time_control(workload, scale_factor, branch):

    # Extract everything from the workload dictionary
    reference_nps = workload['test'][branch]['nps']
    time_control  = workload['test'][branch]['time_control']

    # Searching for Nodes or Depth time controls ("N=", "D=")
    pattern = r'(?P<mode>((N))|(D))=(?P<value>(\d+))'
    results = re.search(pattern, time_control.upper())

    # No scaling is needed for fixed nodes or fixed depth games
    if results:
        mode, value = results.group('mode', 'value')
        return 'tc=inf %s=%s' % ({'N' : 'nodes', 'D' : 'depth'}[mode], value)

    # Searching for MoveTime or Fixed Time Controls ("MT=")
    pattern = r'(?P<mode>(MT))=(?P<value>(\d+))'
    results = re.search(pattern, time_control.upper())

    # Scale the time based on this machine's NPS. Add a time Margin to avoid time losses.
    if results:
        mode, value = results.group('mode', 'value')
        return 'st=%.2f timemargin=250' % ((float(value) * scale_factor / 1000))

    # Searching for "X/Y+Z" time controls
    pattern = r'(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
    results = re.search(pattern, time_control)
    moves, base, inc = results.group('moves', 'base', 'inc')

    # Strip the trailing and leading symbols
    moves = None if moves == '' else moves.rstrip('/')
    inc   = 0.0  if inc   is None else inc.lstrip('+')

    # Scale the time based on this machine's NPS
    base = float(base) * scale_factor
    inc  = float(inc ) * scale_factor

    # Format the time control for cutechess
    if moves is None:
        return 'tc=%.2f+%.2f timemargin=250' % (base, inc)
    return 'tc=%d/%.2f+%.2f timemargin=250' % (int(moves), base, inc)

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
        'focus'          : config.focus,          # List of engines we have a preference to help
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

    # Throw all the way back to the client.py
    if 'Bad Client Version' in response.get('error', ''):
        raise BadVersionException();

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

    payload  = { 'machine_id' : config.machine_id, 'secret' : config.secret_token, 'blacklist' : config.blacklist }
    target   = url_join(config.server, 'clientGetWorkload')
    response = requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

    # Server errors produce garbage back, which we should not alarm a user with
    try: response = response.json()
    except json.decoder.JSONDecodeError:
        raise OpenBenchBadServerResponseException() from None

    # Throw all the way back to the client.py
    if 'Bad Client Version' in response.get('error', ''):
        raise BadVersionException();

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
    download_opening_book(
        config.workload['test']['book']['sha'   ],
        config.workload['test']['book']['source'],
        config.workload['test']['book']['name'  ],
    )

    # Download each NNUE file, throws an exception on corruption
    dev_network  = safe_download_network_weights(config, 'dev' )
    base_network = safe_download_network_weights(config, 'base')

    # Build or download each engine, or exit if an error occured
    dev_name  = safe_download_engine(config, 'dev' , dev_network )
    base_name = safe_download_engine(config, 'base', base_network)

    # Datagen creates a book on-the-fly
    if config.workload['test']['type'] == 'DATAGEN':
        safe_create_genfens_opening_book(config, dev_name, dev_network)

    # Run the benchmarks and compute the scaling NPS value
    dev_nps  = safe_run_benchmarks(config, 'dev' , dev_name , dev_network )
    base_nps = safe_run_benchmarks(config, 'base', base_name, base_network)
    ServerReporter.report_nps(config, dev_nps, base_nps)

    # Scale the engines together, using their NPS relative to expected
    dev_factor  = config.workload['test']['dev' ]['nps'] / dev_nps
    base_factor = config.workload['test']['base']['nps'] / base_nps
    avg_factor  = (dev_factor + base_factor) / 2

    print () # Record this information
    print ('Scale Factor Dev  : %.4f' % (dev_factor ))
    print ('Scale Factor Base : %.4f' % (base_factor))
    print ('Scale Factor Avg  : %.4f' % (avg_factor ))

    # Server knows how many copies of Cutechess we should run
    cutechess_cnt   = config.workload['distribution']['cutechess-count']
    concurrency_per = config.workload['distribution']['concurrency-per']
    games_per       = config.workload['distribution']['games-per-cutechess']

    print () # Record this information
    print ('%d cutechess copies' % (cutechess_cnt))
    print ('%d concurrent games per copy' % (concurrency_per))
    print ('%d total games per cutechess copy\n' % (games_per))

    # Scale using the base factor only, in the event of a cross-engine test
    dev_engine    = config.workload['test']['dev' ]['engine']
    base_engine   = config.workload['test']['base']['engine']
    scale_factor  = base_factor if dev_engine != base_engine else avg_factor

    # Launch and manage all of the Cutechess workers
    with ThreadPoolExecutor(max_workers=cutechess_cnt) as executor:

        timestamp  = time.time()
        results    = multiprocessing.Queue()
        abort_flag = threading.Event()

        tasks = [] # Create each of the Cutechess workers
        for x in range(cutechess_cnt):
            cmd = build_cutechess_command(config, dev_name, base_name, scale_factor, timestamp, x)
            tasks.append(executor.submit(run_and_parse_cutechess, config, cmd, x, results, abort_flag))

        # Process the Queue until we exit, finish, or are told to stop by the server
        try:
            rr = ResultsReporter(config, tasks, results, abort_flag)
            rr.process_until_finished()
            rr.send_errors(timestamp, cutechess_cnt)
            Cutechess.kill_everything(dev_name, base_name)

        # Kill everything during an Exception, but print it
        except (Exception, KeyboardInterrupt):
            traceback.print_exc()
            abort_flag.set()
            Cutechess.kill_everything(dev_name, base_name)
            raise

        # Upload the PGN if requested
        if config.workload['test']['upload_pgns'] != 'FALSE':
            compact    = config.workload['test']['upload_pgns'] == 'COMPACT'
            pgn_files  = [Cutechess.pgn_name(config, timestamp, x) for x in range(cutechess_cnt)]
            ServerReporter.report_pgn(config, compress_list_of_pgns(pgn_files, scale_factor, compact))

def safe_download_network_weights(config, branch):

    # Wraps utils.py:download_network()
    # May raise OpenBenchCorruptedNetworkException

    engine   = config.workload['test'][branch]['engine' ]
    net_name = config.workload['test'][branch]['netname']
    net_sha  = config.workload['test'][branch]['network']
    net_path = os.path.join('Networks', net_sha)

    # Not all engines use Network files
    if not net_sha or net_sha == 'None':
        return None

    credentials = (config.server, config.username, config.password)
    download_network(*credentials, engine, net_name, net_sha, net_path)

    return net_path

def safe_download_engine(config, branch, net_path):

    # Wraps utils.py:download_public_engine() and utils.py:download_private_engine()

    engine      = config.workload['test'][branch]['engine']
    branch_name = config.workload['test'][branch]['name']
    commit_sha  = config.workload['test'][branch]['sha']
    source      = config.workload['test'][branch]['source']
    private     = config.workload['test'][branch]['private']

    bin_name = engine_binary_name(engine, commit_sha, net_path, private)
    out_path = os.path.join('Engines', bin_name)

    if private:

        try:
            return download_private_engine(
                engine, branch_name, source, out_path, config.cpu_name, config.cpu_flags)

        except OpenBenchMissingArtifactException as error:
            ServerReporter.report_missing_artifact(config, branch, error.name, error.logs)
            raise

    else:

        make_path = config.workload['test'][branch]['build']['path']
        compiler  = config.compilers[engine][0]

        try:
            return download_public_engine(
                engine, net_path, branch_name, source, make_path, out_path, compiler)

        except OpenBenchBuildFailedException as error:

            print ('Failed to build %s-%s...\n\nCompiler Output:' % (engine, branch_name))
            for line in error.logs.split('\n'):
                print ('> %s' % (line))
            print ()

            config.blacklist.append(config.workload['test']['id'])
            ServerReporter.report_build_fail(config, branch, error.logs)
            raise

def safe_create_genfens_opening_book(config, dev_name, dev_network):

    try: create_genfens_opening_book(config, dev_name, dev_network)

    except OpenBenchFailedGenfensException as error:
        ServerReporter.report_engine_error(config, error.message)
        raise

def safe_run_benchmarks(config, branch, engine, network):

    name     = config.workload['test'][branch]['name']
    private  = config.workload['test'][branch]['private']
    expected = int(config.workload['test'][branch]['bench'])
    binary   = os.path.join('Engines', engine)

    try:
        print('\nRunning %dx Benchmarks for %s' % (config.threads, name))
        speed, nodes = bench.run_benchmark(
            binary, network, private, config.threads, 1, expected)

    except OpenBenchBadBenchException as error:
        ServerReporter.report_bad_bench(config, error.message)
        raise

    print('Bench for %s is %d' % (name, nodes))
    print('Speed for %s is %d' % (name, speed))
    return speed


def build_cutechess_command(config, dev_cmd, base_cmd, scale_factor, timestamp, cutechess_idx):

    flags  = ' ' + Cutechess.basic_settings(config)
    flags += ' ' + Cutechess.concurrency_settings(config)
    flags += ' ' + Cutechess.adjudication_settings(config)
    flags += ' ' + Cutechess.engine_settings(config, dev_cmd, 'dev', scale_factor, cutechess_idx)
    flags += ' ' + Cutechess.engine_settings(config, base_cmd, 'base', scale_factor, cutechess_idx)
    flags += ' ' + Cutechess.book_settings(config, cutechess_idx)
    flags += ' ' + Cutechess.pgnout_settings(config, timestamp, cutechess_idx)

    return ['cutechess-ob.exe', './cutechess-ob'][IS_LINUX] + flags

def run_and_parse_cutechess(config, command, cutechess_idx, results_queue, abort_flag):

    print('\n[#%d] Launching Cutechess...\n%s\n' % (cutechess_idx, command))
    cutechess = Popen(command.split(), stdout=PIPE)

    results = {

        'trinomial'   : [0, 0, 0],       # LDW
        'pentanomial' : [0, 0, 0, 0, 0], # LL DL DD DW WW
        'games'       : {},              # game_id : result_str

        'crashes'     : 0,               # " disconnect" or "connection stalls"
        'timelosses'  : 0,               # " loses on time "
        'illegals'    : 0,               # " illegal move "
    }

    while True:

        # Read each line of output until the pipe closes and we get "" back
        line = cutechess.stdout.readline().strip().decode('ascii')
        if not line:
            break

        if abort_flag.is_set():
            break

        if 'Started game' not in line and 'Score of' not in line:
            print('[#%d] %s' % (cutechess_idx, line))

        if 'Finished game' in line:
            Cutechess.update_results(results, line)

        # Add to the results queue every time we have a game-pair finished
        if any(results['pentanomial']):

            # Place the results into the Queue, and be sure to copy the lists
            results_queue.put({
                'trinomial'     : list(results['trinomial']),
                'pentanomial'   : list(results['pentanomial']),
                'crashes'       : results['crashes'],
                'timelosses'    : results['timelosses'],
                'illegals'      : results['illegals'],
                'cutechess_idx' : cutechess_idx,
            })

            # Clear out all the results, so we can start collecting a new set
            results['trinomial'  ] = [0, 0, 0]
            results['pentanomial'] = [0, 0, 0, 0, 0]
            results['crashes'    ] = 0
            results['timelosses' ] = 0
            results['illegals'   ] = 0

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#                                                                           #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def parse_arguments(client_args):

    # Pretty formatting
    p = argparse.ArgumentParser(
        formatter_class=lambda prog:
            argparse.ArgumentDefaultsHelpFormatter(prog, max_help_position=10)
    )

    # Arguments specific to worker.py
    p.add_argument('-T', '--threads' , help='Total Threads'           , required=True      )
    p.add_argument('-N', '--nsockets', help='Number of Sockets'       , required=True      )
    p.add_argument('-I', '--identity', help='Machine pseudonym'       , required=False     )
    p.add_argument(      '--syzygy'  , help='Syzygy WDL'              , required=False     )
    p.add_argument(      '--fleet'   , help='Fleet Mode'              , action='store_true')
    p.add_argument(      '--focus'   , help='Prefer certain engine(s)', nargs='+'          )

    # Ignore unknown arguments ( from client )
    worker_args, unknown = p.parse_known_args()

    # Add the client args (Username, Password, and Server) to the worker args
    return argparse.Namespace(**{ **vars(client_args), **vars(worker_args) })

def run_openbench_worker(client_args):

    args   = parse_arguments(client_args) # Merge client.py and worker.py args
    config = Configuration(args)          # Holds System info, args, and Workload info

    setup_error      = '[Note] Unable to establish initial connection with the Server!'
    connection_error = '[Note] Unable to reach the server to request a workload!'

    try_forever(server_configure_worker, [config], setup_error)

    if IS_LINUX:
        set_cutechess_permissions()

    while True:
        try:
            # Cleanup on each workload request
            cleanup_client()

            # Keep asking for a workload until we get a response
            try_forever(server_request_workload, [config], connection_error)

            # Complete the workload if there was work to be done
            if config.workload: complete_workload(config)

            # Otherwise --fleet workers will exit when there is no work
            elif config.fleet: time.sleep(TIMEOUT_ERROR); sys.exit()

            # In either case, wait before requesting again
            else: time.sleep(TIMEOUT_WORKLOAD)

            # Check for exit signal via openbench.exit
            if os.path.isfile('openbench.exit'):
                print('Exited via openbench.exit')
                sys.exit()

        except BadVersionException:
            raise BadVersionException()

        except Exception:
            traceback.print_exc()
            time.sleep(TIMEOUT_ERROR)
