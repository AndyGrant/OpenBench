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
import re
import requests
import shutil
import sys
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
CLIENT_VERSION   = '10' # Client version to send to the Server

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
        p.add_argument('-N', '--ncutechess' , help='Cutechess Copies'  , required=True      )
        p.add_argument('-I', '--identity'   , help='Machine pseudonym' , required=False     )
        p.add_argument(      '--syzygy'     , help='Syzygy WDL'        , required=False     )
        p.add_argument(      '--fleet'      , help='Fleet Mode'        , action='store_true')
        p.add_argument(      '--proxy'      , help='Github Proxy'      , action='store_true')
        args = p.parse_args()

        # Extract all of the options
        self.username = args.username if args.username else os.environ['OPENBENCH_USERNAME']
        self.password = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
        self.server   = args.server
        self.threads  = int(args.threads)
        self.sockets  = int(args.ncutechess)
        self.identity = args.identity if args.identity else 'None'
        self.syzygy   = args.syzygy   if args.syzygy   else None
        self.fleet    = args.fleet    if args.fleet    else False
        self.proxy    = args.proxy    if args.proxy    else False

    def init_client(self):

        # Verify that we have make installed
        print('\nScanning For Basic Utilities...')
        locate_utility('make')

        # Use Client.py's path as the base pathway
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

        # Ensure the folder structure for ease of coding
        for folder in ['PGNs', 'Engines', 'Networks', 'Books']:
            if not os.path.isdir(folder):
                os.mkdir(folder)

        # Verify all WDL tables are present when told they are
        validate_syzygy_exists(self)

    def validate_setup(self):

        assert self.threads >= self.sockets
        assert self.threads % self.sockets == 0
        assert min(self.threads, self.sockets) >= 1

    def scan_for_compilers(self, data):

        print ('\nScanning for Compilers...')

        # For each engine, attempt to find a valid compiler
        for engine, build_info in data.items():

            # Private engines don't need to be compiled
            if 'artifacts' in build_info: continue

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
            if not 'artifacts' in build_info: continue

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
        desired += ['AVX512_VNNI', 'AVX512BW', 'AVX512CD', 'AVX512DQ', 'AVX512F']

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
            'logs'       : compiler_output,
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
    def report_results(config, stats):

        wins, losses, draws, crashes, timelosses = stats

        payload = {
            'test_id'    : config.workload['test']['id'],
            'result_id'  : config.workload['result']['id'],
            'wins'       : wins,
            'losses'     : losses,
            'draws'      : draws,
            'crashes'    : crashes,
            'timeloss'   : timelosses,
        }

        return ServerReporter.report(config, 'clientSubmitResults', payload)


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

    try:
        return get_version(util)

    except Exception:

        if report_error:
            print('[Error] Unable to locate %s' % (util))

        if force_exit:
            sys.exit()

    return False


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

def validate_syzygy_exists(config):

    print('\nScanning for Syzygy Configuration...')

    for filename in tablebase_names():

        # Build the paths when the configuration enables Syzygy
        if config.syzygy:
            wdlpath = os.path.join(config.syzygy, filename + '.rtbw')

        # Reset the configuration if the file is missing
        if config.syzygy and not os.path.isfile(wdlpath):
            config.syzygy = None

    # Report final results, which may conflict with the original configuration
    if config.syzygy:
        print('Verified Syzygy WDL (%s)' % (config.syzygy))
    else: print('Syzygy WDL Not Found')

def tablebase_names(K=6):

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

    return list(filter(valid_filename, set(candidates)))

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

def scale_time_control(workload, nps, branch):

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
        return 'st=%.2f timemargin=100' % ((float(value) * reference_nps) / (1000 * nps))

    # Searching for "X/Y+Z" time controls
    pattern = '(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
    results = re.search(pattern, time_control)
    moves, base, inc = results.group('moves', 'base', 'inc')

    # Strip the trailing and leading symbols
    moves = None if moves == '' else moves.rstrip('/')
    inc   = 0.0  if inc   is None else inc.lstrip('+')

    # Scale the time based on this machine's NPS
    base = float(base) * reference_nps / nps
    inc  = float(inc ) * reference_nps / nps

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

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   All functions used to make requests to the OpenBench server. Workload   #
#   requests require Username and Password authentication. Communication    #
#   with the server is required to succeed except for result uploads which  #
#   may be batched and held onto in the event of outages.                   #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

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
        'ncutechesses'   : config.sockets,        # Cutechess copies, usually equal to Socket count
        'client_ver'     : CLIENT_VERSION,        # Version of the Client, which the server may reject
        'syzygy_wdl'     : bool(config.syzygy),   # Whether or not the machine has Syzygy support
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
    avg_nps  = (dev_nps + base_nps) // 2

    # Report NPS to server, or exit if an error occured
    if not dev_nps or not base_nps: return
    ServerReporter.report_nps(config, dev_nps, base_nps)

    # Launch and manage all of the Cutechess workers
    with ThreadPoolExecutor(max_workers=config.sockets) as executor:

        tasks = [] # Create each of the Cutechess workers
        for x in range(config.sockets):
            cmd = build_cutechess_command(config, dev_name, base_name, avg_nps, x)
            tasks.append(executor.submit(run_and_parse_cutechess, config, cmd, x))

        # Await the completion of all Cutechess workers
        try:
            for task in tasks:
                task.result()

        # Kill everything during an Keyboard Interrupt
        except KeyboardInterrupt:
            for task in tasks: task.cancel()
            raise KeyboardInterrupt

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
    network_name = config.workload['test'][branch]['network']
    if not network_name or network_name == 'None': return None

    # Log that we are obtaining a Neural Network
    pattern = 'Fetching Neural Network [ %s, %-4s ]'
    print(pattern % (network_name, branch.upper()))

    # Fetch the Netural Network if we do not already have it
    network_path = os.path.join('Networks', network_name)
    if not os.path.isfile(network_path):
        target  = url_join(config.server, 'clientGetNetwork')
        payload = { 'username' : config.username, 'password' : config.password }
        download_file(url_join(target, network_name), network_path, payload)

    # Verify the download and delete partial or corrupted ones
    with open(network_path, 'rb') as network:
        sha256 = hashlib.sha256(network.read()).hexdigest()
        sha256 = sha256[:8].upper()
    if network_name != sha256: os.remove(network_path)

    # We have to have the correct Neural Network to continue
    if network_name != sha256:
        raise Exception('Invalid SHA for %s' % (network_name))

    return network_path

def download_engine(arguments, branch, network):

    engine      = config.workload['test'][branch]['engine']
    branch_name = config.workload['test'][branch]['name']
    commit_sha  = config.workload['test'][branch]['sha']
    source      = config.workload['test'][branch]['source']
    build_path  = config.workload['test'][branch]['build']['path']
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
        artifacts = requests.get(url=source, headers=auth_headers).json()['artifacts']

        # For sanity, just avoid using PEXT/BMI2 on AMD Chips
        ryzen = 'AMD' in SYSTEM_CPU_NAME.upper()
        ryzen = 'RYZEN' in SYSTEM_CPU_NAME.upper() or ryzen

        # Construct the artifact string for the desired binary
        os_string  = ['windows', 'linux' ][IS_LINUX]
        avx_string = ['avx2'   , 'avx512']['AVX512_VNNI' in str(SYSTEM_CPU_FLAGS)]
        bit_string = ['popcnt' , 'pext'  ]['BMI2' in str(SYSTEM_CPU_FLAGS) and not ryzen]
        desired    = '%s-%s-%s' % (os_string, avx_string, bit_string)

        # Search for our artifact in the list provided
        artifact_id = None
        for artifact in artifacts:
            if artifact['name'] == '%s-%s' % (commit_sha, desired):
                artifact_id = artifact['id']

        # Artifact was missing, workload cannot be completed
        if artifact_id == None:
            ServerReporter.report_missing_artifact(config, branch, desired, artifacts)
            return None

        # Download the binary that matches our desired artifact
        print ('Downloading [%s] %s' % (branch_name, desired))
        base = source.split('/runs/')[0]
        url  = url_join(base, 'artifacts', str(artifact_id), 'zip').rstrip('/')
        download_file(url, 'artifact.zip', None, auth_headers)

        # Unzip the binary, and determine where to move the binary
        unzip_delete_file('artifact.zip', 'tmp/')
        output_name = os.path.join('tmp', engine.replace(' ', '').lower())

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

    # Execute a benchmark on each of the Threads
    for ii in range(config.threads):
        args = [os.path.join('Engines', engine), queue]
        if private and network: args.append(network)
        multiprocessing.Process(target=run_bench, args=args).start()

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

def build_cutechess_command(config, dev_cmd, base_cmd, nps, socket):

    dev_options  = config.workload['test']['dev' ]['options']
    base_options = config.workload['test']['base']['options']

    dev_threads  = int(extract_option(dev_options,  'Threads'))
    base_threads = int(extract_option(base_options, 'Threads'))

    dev_network  = config.workload['test']['dev' ]['network']
    base_network = config.workload['test']['base']['network']

    dev_time     = scale_time_control(config.workload, nps, 'dev')
    base_time    = scale_time_control(config.workload, nps, 'base')

    dev_name     =  dev_cmd.rstrip('.exe') # Used to name the PGN file and Headers
    base_name    = base_cmd.rstrip('.exe') # Used to name the PGN file and Headers

    # Possibly add SyzygyPath to dev and base options
    if config.syzygy and config.workload['test']['syzygy_wdl'] != 'DISABLED':
        path = SYZYGY_WDL_PATH.replace('\\', '\\\\')
        dev_options  += ' SyzygyPath=%s' % (path)
        base_options += ' SyzygyPath=%s' % (path)

    # Private engines may need extra options to set their NNUE files
    if config.workload['test']['dev']['private'] and dev_network and dev_network != 'None':
        dev_options += ' EvalFile=%s' % (os.path.join('../Networks', dev_network))
        dev_name    += '-%s' % (dev_network)

    # Private engines may need extra options to set their NNUE files
    if config.workload['test']['base']['private'] and base_network and base_network != 'None':
        base_options += ' EvalFile=%s' % (os.path.join('../Networks', base_network))
        base_name    += '-%s' % (base_network)

    # Join all of the options into a single string
    dev_options  = ' option.'.join([''] +  dev_options.split())
    base_options = ' option.'.join([''] + base_options.split())

    # Extract win adjudication settings if there are any
    win_adj = config.workload['test']['win_adj' ]
    win_adj = ['', '-resign ' + win_adj][win_adj != 'None']

    # Extract draw adjudication settings if there are any
    draw_adj = config.workload['test']['draw_adj']
    draw_adj = ['', '-draw ' + draw_adj][draw_adj != 'None']

    # Assume Fischer if FRC or 960 appears in the Opening Book
    book_name = config.workload['test']['book']['name']
    variant   = ['standard', 'fischerandom']['FRC' in book_name.upper() or '960' in book_name]

    # Number of concurrency games that this socket can play
    concurrency = config.threads / config.sockets
    concurrency = concurrency // max(dev_threads, base_threads)

    # Play at least a single game-pair per concurrency
    games = int(concurrency * config.workload['test']['workload_size'])
    games = max(concurrency * 2, games - (games % (2 * concurrency)))

    flags  = '-repeat -recover %s %s '
    flags += '-srand %d -variant %s -concurrency %d -games %d '
    flags += '-engine dir=Engines/ cmd=./%s proto=uci %s%s name=%s '
    flags += '-engine dir=Engines/ cmd=./%s proto=uci %s%s name=%s '
    flags += '-openings file=Books/%s format=%s order=random plies=16 '
    flags += '-pgnout PGNs/%s_vs_%s.%d '

    # Add Syzygy adjudication to Cutechess if its not disabled and we have the WDL
    if config.syzygy and config.workload['test']['syzygy_adj'] != 'DISABLED':
        flags += '-tb %s' % (config.syzygy.replace('\\', '\\\\'))

    args = (
        win_adj, draw_adj,
        int(time.time() + socket), variant, concurrency, games,
        dev_cmd, dev_time, dev_options, dev_name,
        base_cmd, base_time, base_options, base_name,
        book_name, book_name.split('.')[-1],
        dev_name, base_name, socket,
    )

    if IS_LINUX: return './cutechess-ob ' + flags % (args)
    return 'cutechess-ob.exe ' + flags % (args)

def run_and_parse_cutechess(config, command, socket):

    print('\n[#%d] Launching Cutechess...\n%s\n' % (socket, command))
    cutechess = Popen(command.split(), stdout=PIPE)

    crashes = timelosses = 0
    score   = [0, 0, 0]; sent = [0, 0, 0] # WLD
    errors  = ['on time', 'disconnects', 'connection stalls', 'illegal']

    while True:

        # Read each line of output until the pipe closes
        line = cutechess.stdout.readline().strip().decode('ascii')
        if line != '': print('[#%d] %s' % (socket, line))
        else: cutechess.wait(); return

        # Real updates contain a colon
        if ':' not in line: continue

        # Parse for crashes and timelosses
        score_reason = line.split(':')[1]
        timelosses += 'on time' in score_reason
        crashes    += 'disconnects' in score_reason
        crashes    += 'connection stalls' in score_reason

        # Forcefully report any engine failures to the server
        for error in errors:
            if error in score_reason:
                pgn = find_pgn_error(score_reason, command)
                ServerReporter.report_engine_error(config, line, pgn)

        # All remaining processing is for score updates only
        if not line.startswith('Score of'):
            continue

        # Only report scores after every eight games
        score = list(map(int, score_reason.split()[0:5:2]))
        if ((sum(score) - sum(sent)) % config.workload['test']['report_rate'] != 0):
            continue

        try:
            # Report new results to the server
            wld    = [score[ii] - sent[ii] for ii in range(3)]
            stats  = wld + [crashes, timelosses]
            status = ServerReporter.report_results(config, stats).json()

            # Reset the reporting since this report was a success
            crashes = timelosses = 0
            sent    = score[::]

        except:
            # Failed to connect, but we can delay the reports until later
            print('[NOTE] Unable To Reach Server');

        # Check for openbench.exit, or server instructing us to exit
        if os.path.isfile('openbench.exit') or 'stop' in status:
            kill_cutechess(cutechess)
            return

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
