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

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   Configuration for the Client. To disable deleting old files, use the    #
#   value None. If Syzygy Tablebases are not present, set to None.          #
#                                                                           #
#   Each engine allows a custom set of arguments. All engines will compile  #
#   without any custom options. However you have the ability to add args    #
#   in order to get better builds, like PGO or PEXT/BMI2.                   #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

TIMEOUT_HTTP     = 30    # Timeout in seconds for HTTP requests
TIMEOUT_ERROR    = 10    # Timeout in seconds when any errors are thrown
TIMEOUT_WORKLOAD = 30    # Timeout in seconds between workload requests
CLIENT_VERSION   = '7'   # Client version to send to the Server

SYZYGY_WDL_PATH  = None  # Pathway to WDL Syzygy Tables
FLEET_MODE       = False # Exit when there are no workloads

ERRORS = {
    'cutechess' : 'Unable to fetch Cutechess location and download it!',
    'configure' : 'Unable to fetch and determine acceptable workloads!',
    'request'   : 'Unable to reach server for workload request!',
}

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   Setting up the Client. Build the OpenBench file structure, check for    #
#   Syzygy Tables for both WDL (Adjudication, and Gameplay). Download a     #
#   static Cutechess binary,  and determine what engines we are able to     #
#   compile by asking the server for compiler and CPU Flag requirements     #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Differentiate Windows and Linux systems
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX   = platform.system() != 'Windows'

COMPILERS = {} # Compiler for each Engine, + CPU Flags
CPUINFO   = '' # Result of ``echo | gcc -march=native -E -dM -``
OSNAME    = '%s %s' % (platform.system(), platform.release())
DEBUG     = True

SYSTEM_COMPILERS      = {}
SYSTEM_GIT_TOKENS     = {}
SYSTEM_CPU_FLAGS      = []
SYSTEM_CPU_NAME       = ''
SYSTEM_OS_NAME        = platform.system()
SYSTEM_OS_VER         = platform.release()
SYSTEM_PYTHON_VER     = platform.python_version()
SYSTEM_MAC_ADDRESS    = hex(uuid.getnode()).upper()[2:]
SYSTEM_LOGICAL_CORES  = psutil.cpu_count(logical=True)
SYSTEM_PHYSICAL_CORES = psutil.cpu_count(logical=False)
SYSTEM_RAM_TOTAL_MB   = psutil.virtual_memory().total // (1024 ** 2)
SYSTEM_MACHINE_ID     = 'None'
SYSTEM_SECRET_TOKEN   = 'None'

def get_version(program):

    # Try to execute the program from the command line
    # First with `--version`, and again with just `version`

    try:
        process = Popen([program, '--version'], stdout=PIPE, stderr=PIPE)
        stdout = process.communicate()[0].decode('utf-8')
        return re.search(r'\d+\.\d+(\.\d+)?', stdout).group()

    except:
        process = Popen([program, 'version'], stdout=PIPE, stderr=PIPE)
        stdout = process.communicate()[0].decode('utf-8')
        return re.search(r'\d+\.\d+(\.\d+)?', stdout).group()

def locate_utility(util, force_exit=True, report_error=True, report_found=True):

    try:
        version = get_version(util)
        if report_found:
            print('Located %s (%s)' % (util, version))
        return version

    except Exception:
        if report_error:
            print('[Error] Unable to locate %s' % (util))
        if force_exit:
            sys.exit()
        return False


def scan_for_compilers(data):

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
                    SYSTEM_COMPILERS[engine] = (compiler, match)
                    break
            except: continue # Unable to execute compiler

        # Report missing engines in case the User is not expecting it
        if engine not in SYSTEM_COMPILERS:
            print('%-16s | Missing %s' % (engine, data[engine]['compilers']))

def scan_for_private_tokens(data):

    print ('\nScanning for Private Tokens...')

    # For each engine, attempt to find a valid compiler
    for engine, build_info in data.items():

        # Public engines don't need access tokens
        if not build_info['private']: continue

        # Private engines expect a credentials.engine file for the main repo
        has_token = os.path.exists('credentials.%s' % (engine.replace(' ', '').lower()))
        print('%-16s | %s' % (engine, ['Missing', 'Found'][has_token]))
        if has_token: SYSTEM_GIT_TOKENS[engine] = True

def scan_for_cpu_flags(data):

    print('\nScanning for CPU Flags...')

    # Get all flags, and for sanity uppercase them
    info   = cpuinfo.get_cpu_info()
    actual = [x.upper() for x in info['flags']]

    # Set the CPU name which has to be done via global
    global SYSTEM_CPU_NAME, SYSTEM_CPU_FLAGS
    SYSTEM_CPU_NAME = info['brand_raw']

    # This should cover virtually all compiler flags that we would care about
    desired  = ['POPCNT', 'BMI2']
    desired += ['SSSE3', 'SSE4_1', 'SSE4_2', 'SSE4A', 'AVX', 'AVX2', 'FMA']
    desired += ['AVX512_VNNI', 'AVX512BW', 'AVX512CD', 'AVX512DQ', 'AVX512F']

    # Add any custom flags from the OpenBench configs, just in case we missed one
    requested = set(sum([info['cpuflags'] for engine, info in data.items()], []))
    for flag in [x for x in requested if x not in desired]: desired.append(flag)
    SYSTEM_CPU_FLAGS = [x for x in desired if x in actual]

    # Report the results of our search, including any "missing flags
    print ('Found   | ', ' '.join(SYSTEM_CPU_FLAGS))
    print ('Missing | ', ' '.join([x for x in desired if x not in actual]))

def scan_for_machine_id():

    # If we don't have one, the server will give us one, and then include it
    # in future HTTP responses. We simply need to save the a .txt file, later

    global SYSTEM_MACHINE_ID

    if os.path.isfile('machine.txt'):
        with open('machine.txt') as fin:
            SYSTEM_MACHINE_ID = fin.readlines()[0]

    if SYSTEM_MACHINE_ID == 'None':
        print('[NOTE] This machine is currently unregistered')


def init_client(arguments):

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
    validate_syzygy_exists()

def cleanup_client():

    SECONDS_PER_DAY   = 60 * 60 * 24
    SECONDS_PER_MONTH = SECONDS_PER_DAY * 30

    file_age = lambda x: time.time() - os.path.getmtime(x)

    for file in os.listdir('PGNs'):
        if file_age(os.path.join('PGNs', file)) > SECONDS_PER_DAY:
            os.remove(os.path.join('PGNs', file))

    for file in os.listdir('Engines'):
        if file_age(os.path.join('Engines', file)) > SECONDS_PER_DAY:
            os.remove(os.path.join('Engines', file))

    for file in os.listdir('Networks'):
        if file_age(os.path.join('Networks', file)) > SECONDS_PER_MONTH:
            os.remove(os.path.join('Networks', file))

def validate_syzygy_exists():

    global SYZYGY_WDL_PATH

    print('\nScanning for Syzygy Configuration...')

    for filename in tablebase_names():

        # Build the paths when the configuration enables Syzygy
        if SYZYGY_WDL_PATH:
            wdlpath = os.path.join(SYZYGY_WDL_PATH, filename + '.rtbw')

        # Reset the configuration if the file is missing
        if SYZYGY_WDL_PATH and not os.path.isfile(wdlpath):
            SYZYGY_WDL_PATH = None

    # Report final results, which may conflict with the original configuration
    if SYZYGY_WDL_PATH:
        print('Verified Syzygy WDL (%s)' % (SYZYGY_WDL_PATH))
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


def url_join(*args):

    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + '/'

def try_until_success(mesg):
    def _try_until_success(funct):
        def __try_until_success(*args):
            while True:
                try: return funct(*args)
                except Exception:
                    print('[Error]', mesg);
                    if FLEET_MODE: sys.exit()
                    time.sleep(TIMEOUT_ERROR)
                    if DEBUG: traceback.print_exc()
        return __try_until_success
    return _try_until_success

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


def make_command(arguments, engine, src_path, network_path):

    command = 'make %s=%s EXE=%s -j%d' % (
        ['CC', 'CXX']['++' in SYSTEM_COMPILERS[engine]], SYSTEM_COMPILERS[engine], engine, arguments.threads)

    if network_path != None:
        path = os.path.relpath(os.path.abspath(network_path), src_path)
        command += ' EVALFILE=%s' % (path.replace('\\', '/'))

    return command.split()

def parse_bench_output(stream):

    nps = bench = None # Search through output Stream
    for line in stream.decode('ascii').strip().split('\n')[::-1]:

        # Try to match a wide array of patterns
        line = re.sub(r'[^a-zA-Z0-9 ]+', ' ', line)
        nps_pattern = r'([0-9]+ NPS)|(NPS[ ]+[0-9]+)'
        bench_pattern = r'([0-9]+ NODES)|(NODES[ ]+[0-9]+)'
        re_nps = re.search(nps_pattern, line.upper())
        re_bench = re.search(bench_pattern, line.upper())

        # Replace only if not already found earlier
        if not nps and re_nps: nps = re_nps.group()
        if not bench and re_bench: bench = re_bench.group()

    # Parse out the integer portion from our matches
    nps = int(re.search(r'[0-9]+', nps).group()) if nps else None
    bench = int(re.search(r'[0-9]+', bench).group()) if bench else None
    return (nps, bench)

def run_bench(engine, outqueue, private_net=None):

    try:
        # We may need to set an EvalFile via the UCI Options
        if not private_net: cmd = ['./' + engine, 'bench']
        else: cmd = ['./' + engine, 'setoption name EvalFile value %s' % (private_net), 'bench', 'quit']

        # Launch the engine and parse output for statistics
        process = Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        outqueue.put(parse_bench_output(stdout))
    except Exception: outqueue.put((0, 0))

def scale_time_control(workload, nps):

    # Searching for Nodes or Depth time controls ("N=", "D=")
    pattern = '(?P<mode>((N))|(D))=(?P<value>(\d+))'
    results = re.search(pattern, workload['test']['timecontrol'].upper())

    # No scaling is needed for fixed nodes or fixed depth games
    if results:
        mode, value = results.group('mode', 'value')
        return 'tc=inf %s=%s' % ({'N' : 'nodes', 'D' : 'depth'}[mode], value)

    # Searching for MoveTime or Fixed Time Controls ("MT=")
    pattern = '(?P<mode>(MT))=(?P<value>(\d+))'
    results = re.search(pattern, workload['test']['timecontrol'].upper())

    # Scale the time based on this machine's NPS. Add a time Margin to avoid time losses.
    if results:
        mode, value = results.group('mode', 'value')
        return 'st=%.2f timemargin=100' % (float(value) * int(workload['test']['nps']) / (1000 * nps))

    # Searching for "X/Y+Z" time controls
    pattern = '(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
    results = re.search(pattern, workload['test']['timecontrol'])
    moves, base, inc = results.group('moves', 'base', 'inc')

    # Strip the trailing and leading symbols
    moves = None if moves == '' else moves.rstrip('/')
    inc   = 0.0  if inc   is None else inc.lstrip('+')

    # Scale the time based on this machine's NPS
    base = float(base) * int(workload['test']['nps']) / nps
    inc  = float(inc ) * int(workload['test']['nps']) / nps

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

@try_until_success(mesg=ERRORS['cutechess'])
def server_download_cutechess(arguments):

    print('\nFetching Cutechess Binary...')

    if IS_WINDOWS and not locate_utility('cutechess-ob.exe', False, False):

        # Fetch the source location if we are missing the binary
        source = requests.get(
            url_join(arguments.server, 'clientGetFiles'),
            timeout=TIMEOUT_HTTP).content.decode('utf-8')

        if arguments.proxy: source = 'https://ghproxy.com/' + source

        # Windows workers simply need a static compile (64-bit)
        download_file(url_join(source, 'cutechess-windows.exe').rstrip('/'), 'cutechess-ob.exe')

        # Verify that we can execute Cutechess
        if not locate_utility('cutechess-ob.exe', False):
            raise Exception

    if IS_LINUX and not locate_utility('./cutechess-ob', False, False):

        # Fetch the source location if we are missing the binary
        source = requests.get(
            url_join(arguments.server, 'clientGetFiles'),
            timeout=TIMEOUT_HTTP).content.decode('utf-8')

        if arguments.proxy: source = 'https://ghproxy.com/' + source

        # Linux workers need a static compile (64-bit) with execute permissions
        download_file(url_join(source, 'cutechess-linux').rstrip('/'), 'cutechess-ob')
        os.system('chmod 777 cutechess-ob')

        # Verify that we can execute Cutechess
        if not locate_utility('./cutechess-ob', False):
            raise Exception

@try_until_success(mesg=ERRORS['configure'])
def server_configure_worker(arguments):

    # Server tells us how to build or obtain binaries
    target = url_join(arguments.server, 'clientGetBuildInfo')
    data   = requests.get(target, timeout=TIMEOUT_HTTP).json()

    scan_for_compilers(data)      # Public engines
    scan_for_private_tokens(data) # Private engines
    scan_for_cpu_flags(data)      # For executing binaries
    scan_for_machine_id()         # None, or the content of machine.txt

    system_info = {
        'compilers'      : SYSTEM_COMPILERS,      # Key: Engine, Value: (Compiler, Version)
        'tokens'         : SYSTEM_GIT_TOKENS,     # Key: Engine, Value: True, for tokens we have
        'cpu_flags'      : SYSTEM_CPU_FLAGS,      # List of CPU flags found in the Client or Server
        'cpu_name'       : SYSTEM_CPU_NAME,       # Raw CPU name as per py-cpuinfo
        'os_name'        : SYSTEM_OS_NAME,        # Should be Windows, Linux, or Darwin
        'os_ver'         : SYSTEM_OS_VER,         # Release version of the OS
        'python_ver'     : SYSTEM_PYTHON_VER,     # Python version running the Client
        'mac_address'    : SYSTEM_MAC_ADDRESS,    # Used to softly verify the Machine IDs
        'logical_cores'  : SYSTEM_LOGICAL_CORES,  # Logical cores, to differentiate hyperthreads
        'physical_cores' : SYSTEM_PHYSICAL_CORES, # Physical cores, to differentiate hyperthreads
        'ram_total_mb'   : SYSTEM_RAM_TOTAL_MB,   # Total RAM on the system, to avoid over assigning
        'machine_id'     : SYSTEM_MACHINE_ID,     # Assigned value, or None. Will be replaced if wrong
        'concurrency'    : arguments.threads,     # Threads to use to play games
        'ncutechesses'   : arguments.ncutechess,  # Cutechess copies, usually equal to Socket count
        'client_ver'     : CLIENT_VERSION,        # Version of the Client, which the server may reject
        'syzygy_wdl'     : bool(SYZYGY_WDL_PATH), # Whether or not the machine has Syzygy support
    }

    payload = {
        'username'    : arguments.username,
        'password'    : arguments.password,
        'system_info' : json.dumps(system_info),
    }

    # Send all of this to the server, and get a Machine Id + Secret Token
    target   = url_join(arguments.server, 'clientWorkerInfo')
    response = requests.post(target, data=payload, timeout=TIMEOUT_HTTP).json()

    # The 'error' header is included if there was an issue
    if 'error' in response:
        print('[Error] %s\n' % (response['error']))
        sys.exit()

    # Save the machine id, to avoid re-registering every time
    with open('machine.txt', 'w') as fout:
        fout.write(str(response['machine_id']))

    # Save the secret token, to send with all future requests
    global SYSTEM_SECRET_TOKEN
    SYSTEM_SECRET_TOKEN = response['secret']

@try_until_success(mesg=ERRORS['request'])
def server_request_workload(arguments):

    print('\nRequesting Workload from Server...')

    supported  = ' '.join(COMPILERS.keys() - ['cpuflags'])

    payload = {
        'username'   : arguments.username, 'threads'    : arguments.threads,
        'password'   : arguments.password, 'ncutechess' : arguments.ncutechess,
        'machineid'  : machine_id,         'osname'     : OSNAME,
        'supported'  : supported,          'syzygy_wdl' : bool(SYZYGY_WDL_PATH),
        'version'    : CLIENT_VERSION,     'cpuflags'   : COMPILERS['cpuflags'],
    }

    target = url_join(arguments.server, 'clientGetWorkload')
    return requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

def server_report_missing_artifact(arguments, workload, branch, artifact_name, artifact_json):

    payload = {
        'username'  : arguments.username,
        'password'  : arguments.password,
        'testid'    : workload['test']['id'],
        'machineid' : workload['machine']['id'],
        'error'     : 'Artifact %s missing' % (artifact_name),
        'logs'      : json.dumps(artifact_json, indent=2),
    }

    target = url_join(arguments.server, 'clientSubmitError')
    requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

def server_report_build_fail(arguments, workload, branch, compiler_output):

    payload = {
        'username'  : arguments.username,
        'password'  : arguments.password,
        'testid'    : workload['test']['id'],
        'machineid' : workload['machine']['id'],
        'error'     : '%s build failed' % (workload['test'][branch]['name']),
        'logs'      : compiler_output,
    }

    target = url_join(arguments.server, 'clientSubmitError')
    requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

def server_report_bad_bench(arguments, workload, branch, bench):

    branch = workload['test'][branch]

    data = {
        'username' : arguments.username, 'testid'    : workload['test']['id'],
        'password' : arguments.password, 'machineid' : workload['machine']['id'],
        'correct'  : branch['bench'],    'engine'    : branch['name'],
        'wrong'    : bench,
    }

    target = url_join(arguments.server, 'clientWrongBench')
    requests.post(target, data=data, timeout=TIMEOUT_HTTP)

def server_report_nps(arguments, workload, dev_nps, base_nps):

    data = {
        'username'  : arguments.username,
        'password'  : arguments.password,
        'machineid' : workload['machine']['id'],
        'nps'       : (dev_nps + base_nps) // 2
    }

    target = url_join(arguments.server, 'clientSubmitNPS')
    requests.post(target, data=data, timeout=TIMEOUT_ERROR)

def server_report_engine_error(arguments, workload, cutechess_str, pgn):

    pairing = cutechess_str.split('(')[1].split(')')[0]
    white, black = pairing.split(' vs ')

    error = cutechess_str.split('{')[1].rstrip().rstrip('}')
    error = error.replace('White', '-'.join(white.split('-')[1:]).rstrip())
    error = error.replace('Black', '-'.join(black.split('-')[1:]).rstrip())

    payload = {
        'username'  : arguments.username,
        'password'  : arguments.password,
        'testid'    : workload['test']['id'],
        'machineid' : workload['machine']['id'],
        'error'     : error,
        'logs'      : pgn,
    }

    target = url_join(arguments.server, 'clientSubmitError')
    requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

def server_report_results(arguments, workload, stats):

    wins, losses, draws, crashes, timelosses = stats

    payload = {
        'username'  : arguments.username,        'wins'      : wins,
        'password'  : arguments.password,        'losses'    : losses,
        'machineid' : workload['machine']['id'], 'draws'     : draws,
        'resultid'  : workload['result']['id'],  'crashes'   : crashes,
        'testid'    : workload['test']['id'],    'timeloss'  : timelosses,
    }

    target = url_join(arguments.server, 'clientSubmitResults')
    try: return requests.post(target, data=payload, timeout=TIMEOUT_HTTP).text
    except: print('[NOTE] Unable To Reach Server'); return 'Unable'

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#                                                                           #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def check_workload_response(arguments, response):

    raw_text = response.content.decode('utf-8')

    # No workloads available to our machine
    if raw_text == 'None':
        print('[NOTE] Server Has No Work')
        if not FLEET_MODE: time.sleep(TIMEOUT_WORKLOAD)
        return False

    # Bad login, kill the worker since all requests will fail
    if raw_text == 'Bad Credentials':
        print('[Error] Invalid Login Credentials')
        sys.exit()

    # Bad machine, mostly meaningless but note it
    if raw_text == 'Bad Machine':
        print('[NOTE] Replacing Invalid Machine Id')
        os.remove('machine.txt')
        return False

    # We must match the server's version number
    if raw_text == 'Bad Client Version':
        print('[ERROR] Client Version Outdated')
        sys.exit()

    # Final check that we may parse the workload JSON
    data = response.json()
    with open('machine.txt', 'w') as fout:
        fout.write(str(data['machine']['id']))

    # Log the start of the new workload
    engine = data['test']['engine']
    dev    = data['test']['dev'   ]['name']
    base   = data['test']['base'  ]['name']
    print('Workload [%s] %s vs %s\n' % (engine, dev, base))

    return data

def complete_workload(arguments, workload):

    dev_network  = download_network_weights(arguments, workload, 'dev' )
    base_network = download_network_weights(arguments, workload, 'base')

    dev_name  = download_engine(arguments, workload, 'dev' , dev_network )
    base_name = download_engine(arguments, workload, 'base', base_network)
    if dev_name == None or base_name == None: return

    dev_bench,  dev_nps  = run_benchmarks(arguments, workload, 'dev' , dev_name , dev_network )
    base_bench, base_nps = run_benchmarks(arguments, workload, 'base', base_name, base_network)
    average_nps          = (dev_nps + base_nps) // 2

    dev_status  = verify_benchmarks(arguments, workload, 'dev' , dev_bench )
    base_status = verify_benchmarks(arguments, workload, 'base', base_bench)

    if not dev_status or not base_status: return
    server_report_nps(arguments, workload, dev_nps, base_nps)
    download_opening_book(arguments, workload)

    # Construct each individual Cutechess argument, which differs by PGN output
    cutechess_args = [
        build_cutechess_command(arguments, workload, dev_name, base_name, average_nps, ii)
        for ii in range(int(arguments.ncutechess))
    ]

    # Create a process for the each copy of run_and_parse_cutechess()
    processes = [
        multiprocessing.Process(
            target=run_and_parse_cutechess,
            args=(arguments, workload, *cutechess_args[ii], ii))
        for ii in range(int(arguments.ncutechess))
    ]

    try:
        # Launch and wait for each cutechess copy
        for process in processes: process.start()
        for process in processes: process.join()

    except KeyboardInterrupt:
        # Kill everything and pass the error back up
        for process in processes: process.kill()
        raise KeyboardInterrupt

def download_opening_book(arguments, workload):

    # Log our attempts to download and verify the book
    book_sha256 = workload['test']['book']['sha'   ]
    book_source = workload['test']['book']['source']
    book_name   = workload['test']['book']['name'  ]
    book_path   = os.path.join('Books', book_name)
    print('\nFetching Opening Book [%s]' % (book_name))

    # Download file if we do not already have it
    if not os.path.isfile(book_path):
        if arguments.proxy: book_source = 'https://ghproxy.com/' + book_source
        download_file(book_source, book_name + '.zip')
        unzip_delete_file(book_name + '.zip', 'Books/')

    # Verify SHAs match with the server
    with open(book_path) as fin:
        content = fin.read().encode('utf-8')
        sha256 = hashlib.sha256(content).hexdigest()
    if book_sha256 != sha256: os.remove(book_path)

    # Log SHAs on every workload
    print('Correct  SHA256 %s' % (book_sha256.upper()))
    print('Download SHA256 %s' % (     sha256.upper()))

    # We have to have the correct SHA to continue
    if book_sha256 != sha256:
        raise Exception('Invalid SHA for %s' % (book_name))

def download_network_weights(arguments, workload, branch):

    # Some tests may not use Neural Networks
    network_name = workload['test'][branch]['network']
    if not network_name or network_name == 'None': return None

    # Log that we are obtaining a Neural Network
    pattern = 'Fetching Neural Network [ %s, %-4s ]'
    print(pattern % (network_name, branch.upper()))

    # Neural Network requests require authorization
    payload = {
        'username' : arguments.username,
        'password' : arguments.password,
    }

    # Fetch the Netural Network if we do not already have it
    network_path = os.path.join('Networks', network_name)
    if not os.path.isfile(network_path):
        api = url_join(arguments.server, 'clientGetNetwork')
        download_file(url_join(api, network_name), network_path, payload)

    # Verify the download and delete partial or corrupted ones
    with open(network_path, 'rb') as network:
        sha256 = hashlib.sha256(network.read()).hexdigest()
        sha256 = sha256[:8].upper()
    if network_name != sha256: os.remove(network_path)

    # We have to have the correct Neural Network to continue
    if network_name != sha256:
        raise Exception('Invalid SHA for %s' % (network_name))

    return network_path

def download_engine(arguments, workload, branch, network):

    engine      = workload['test']['engine']
    branch_name = workload['test'][branch]['name']
    commit_sha  = workload['test'][branch]['sha']
    source      = workload['test'][branch]['source']
    build_path  = workload['test']['build']['path']
    private     = workload['engine']['private']

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

        # Construct the artifact string for the desired binary
        old_ryzen  = '__znver1' in str(CPUINFO) or '__znver2' in str(CPUINFO)
        os_string  = ['windows', 'linux' ][IS_LINUX]
        avx_string = ['avx2'   , 'avx512']['__AVX512VNNI__ 1' in str(CPUINFO)]
        bit_string = ['popcnt' , 'pext'  ]['__BMI2__ 1' in str(CPUINFO) and not old_ryzen]
        desired    = '%s-%s-%s' % (os_string, avx_string, bit_string)

        # Search for our artifact in the list provided
        artifact_id = None
        for artifact in artifacts:
            if artifact['name'] == '%s-%s' % (commit_sha, desired):
                artifact_id = artifact['id']

        # Artifact was missing, workload cannot be completed
        if artifact_id == None:
            server_report_missing_artifact(arguments, workload, branch, desired, artifacts)
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
        command     = make_command(arguments, engine, src_path, network)
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
        server_report_build_fail(arguments, workload, branch, cxx_output)
        return None

def run_benchmarks(arguments, workload, branch, engine, network):

    cores   = arguments.threads
    queue   = multiprocessing.Queue()
    name    = workload['test'][branch]['name']
    private = workload['engine']['private']
    print('\nRunning %dx Benchmarks for %s' % (cores, name))

    for ii in range(cores):
        args = [os.path.join('Engines', engine), queue]
        if private and network: args.append(network)
        multiprocessing.Process(target=run_bench, args=args).start()

    nps, bench = list(zip(*[queue.get() for ii in range(cores)]))
    if len(set(bench)) > 1: return (0, 0) # Flag an error

    print('Bench for %s is %d' % (name, bench[0]))
    print('Speed for %s is %d' % (name, sum(nps) // cores))
    return bench[0], sum(nps) // cores

def verify_benchmarks(arguments, workload, branch, bench):
    if bench != int(workload['test'][branch]['bench']):
        server_report_bad_bench(arguments, workload, branch, bench)
    return bench == int(workload['test'][branch]['bench'])

def build_cutechess_command(arguments, workload, dev_cmd, base_cmd, nps, cutechess_idx):

    dev_options  = workload['test']['dev' ]['options']
    base_options = workload['test']['base']['options']

    dev_threads  = int(re.search('(?<=Threads=)\d*', dev_options ).group())
    base_threads = int(re.search('(?<=Threads=)\d*', base_options).group())

    dev_name  =  dev_cmd.rstrip('.exe') # Used to name the PGN file and Headers
    base_name = base_cmd.rstrip('.exe') # Used to name the PGN file and Headers

    # Possibly add SyzygyPath to dev and base options
    if SYZYGY_WDL_PATH and workload['test']['syzygy_wdl'] != 'DISABLED':
        path = SYZYGY_WDL_PATH.replace('\\', '\\\\')
        dev_options  += ' SyzygyPath=%s' % (path)
        base_options += ' SyzygyPath=%s' % (path)

    # Add EvalFile to the options for Private engines using Networks
    if workload['engine']['private']:

        dev_network  = workload['test']['dev' ]['network']
        if dev_network and dev_network != 'None':
            dev_options += ' EvalFile=%s' % (os.path.join('../Networks', dev_network))
            dev_name    += '-%s' % (dev_network)

        base_network = workload['test']['base']['network']
        if base_network and base_network != 'None':
            base_options += ' EvalFile=%s' % (os.path.join('../Networks', base_network))
            base_name    += '-%s' % (base_network)

    # Join all of the options into a single string
    dev_options  = ' option.'.join([''] +  dev_options.split())
    base_options = ' option.'.join([''] + base_options.split())

    win_adj  = ['', '-resign ' + workload['test']['win_adj' ]][workload['test']['win_adj' ] != 'None']
    draw_adj = ['', '-draw '   + workload['test']['draw_adj']][workload['test']['draw_adj'] != 'None']

    book_name = workload['test']['book']['name']
    variant   = ['standard', 'fischerandom']['FRC' in book_name.upper()]

    flags  = '-repeat -recover %s %s '
    flags += '-srand %d -variant %s -concurrency %d -games %d '
    flags += '-engine dir=Engines/ cmd=./%s proto=uci %s%s name=%s '
    flags += '-engine dir=Engines/ cmd=./%s proto=uci %s%s name=%s '
    flags += '-openings file=Books/%s format=%s order=random plies=16 '
    flags += '-pgnout PGNs/%s_vs_%s.%d '

    if SYZYGY_WDL_PATH and workload['test']['syzygy_adj'] != 'DISABLED':
        flags += '-tb %s' % (SYZYGY_WDL_PATH.replace('\\', '\\\\'))

    concurrency = arguments.threads / arguments.ncutechess
    concurrency = concurrency // max(dev_threads, base_threads)

    games = int(concurrency * workload['test']['workload_size'])
    games = max(8, concurrency * 2, games - (games % (2 * concurrency)))

    time_control = scale_time_control(workload, nps)

    args = (
        win_adj, draw_adj,
        int(time.time() + cutechess_idx), variant, concurrency, games,
        dev_cmd, time_control, dev_options, dev_name,
        base_cmd, time_control, base_options, base_name,
        book_name, book_name.split('.')[-1],
        dev_name, base_name, cutechess_idx,
    )

    if IS_LINUX:
        return concurrency, './cutechess-ob ' + flags % (args)
    return concurrency, 'cutechess-ob.exe ' + flags % (args)

def run_and_parse_cutechess(arguments, workload, concurrency, command, cutechess_idx):

    print('\n[#%d] Launching Cutechess...\n%s\n' % (cutechess_idx, command))
    cutechess = Popen(command.split(), stdout=PIPE)

    crashes = timelosses = 0
    score   = [0, 0, 0]; sent = [0, 0, 0] # WLD
    errors  = ['on time', 'disconnects', 'connection stalls', 'illegal']

    while True:

        # Read each line of output until the pipe closes
        line = cutechess.stdout.readline().strip().decode('ascii')
        if line != '': print('[#%d] %s' % (cutechess_idx, line))
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
                server_report_engine_error(arguments, workload, line, pgn)

        # All remaining processing is for score updates only
        if not line.startswith('Score of'):
            continue

        # Only report scores after every eight games
        score = list(map(int, score_reason.split()[0:5:2]))
        if ((sum(score) - sum(sent)) % workload['test']['report_rate'] != 0): continue

        # Report to the server but allow failed reports to delay
        wld = [score[ii] - sent[ii] for ii in range(3)]
        stats = wld + [crashes, timelosses]
        status = server_report_results(arguments, workload, stats)

        # Check for the task being aborted, or Client being killed
        if status.upper() == 'STOP' or os.path.isfile('openbench.exit'):
            kill_cutechess(cutechess)
            return

        # If the update was succesful reset the results
        if status.upper() != 'UNABLE':
            crashes = timelosses = 0
            sent = score[::]

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#                                                                           #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

if __name__ == '__main__':

    req_user  = required=('OPENBENCH_USERNAME' not in os.environ)
    req_pass  = required=('OPENBENCH_PASSWORD' not in os.environ)
    help_user = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'

    p = argparse.ArgumentParser()

    # Required arguments
    p.add_argument('-U', '--username'   , help=help_user           , required=req_user)
    p.add_argument('-P', '--password'   , help=help_pass           , required=req_pass)
    p.add_argument('-S', '--server'     , help='Webserver Address' , required=True)
    p.add_argument('-T', '--threads'    , help='Total Threads'     , required=True)
    p.add_argument('-N', '--ncutechess' , help='Cutechess Copies'  , required=True)

    # Optional arguments
    p.add_argument('--syzygy', help='Syzygy WDL'  , required=False)
    p.add_argument('--fleet' , help='Fleet Mode'  , action='store_true')
    p.add_argument('--proxy' , help='Github Proxy', action='store_true')

    arguments = p.parse_args()

    arguments.threads = int(arguments.threads)
    arguments.ncutechess = int(arguments.ncutechess)

    # Make sure the thread distibution between Cutechess copies is correct
    assert (arguments.threads >= 1)
    assert (arguments.ncutechess >= 1)
    assert (arguments.threads >= arguments.ncutechess)
    assert (arguments.threads % arguments.ncutechess == 0)

    if arguments.username is None:
        arguments.username = os.environ['OPENBENCH_USERNAME']

    if arguments.password is None:
        arguments.password = os.environ['OPENBENCH_PASSWORD']

    if arguments.syzygy is not None:
        SYZYGY_WDL_PATH = arguments.syzygy

    if arguments.fleet:
        FLEET_MODE = True

    init_client(arguments)
    server_download_cutechess(arguments)
    server_configure_worker(arguments)

    exit(1)

    while True:

        try:
            # Request a new workload
            cleanup_client()
            response = server_request_workload(arguments)
            workload = check_workload_response(arguments, response)

            # Fleet workers exit when there are no workloads
            if workload: complete_workload(arguments, workload)
            elif FLEET_MODE: break

            # Check for exit signal via openbench.exit
            if os.path.isfile('openbench.exit'):
                print('Exited via openbench.exit')
                break

        except Exception: traceback.print_exc()
