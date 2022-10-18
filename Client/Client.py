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
import hashlib
import os
import platform
import re
import requests
import sys
import time
import traceback
import zipfile
import shutil
import multiprocessing

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

TIMEOUT_HTTP        = 30    # Timeout in seconds for HTTP requests
TIMEOUT_ERROR       = 10    # Timeout in seconds when any errors are thrown
TIMEOUT_WORKLOAD    = 30    # Timeout in seconds between workload requests
CLIENT_VERSION      = '3'   # Client version to send to the Server

SYZYGY_WDL_PATH     = None  # Pathway to WDL Syzygy Tables
BASE_GAMES_PER_CORE = 32    # Typical games played per-thread
FLEET_MODE          = False # Exit when there are no workloads

CUSTOM_SETTINGS = {
    'Ethereal'    : [], 'Laser'     : [],
    'Weiss'       : [], 'Demolito'  : [],
    'Rubichess'   : [], 'FabChess'  : [],
    'Igel'        : [], 'Winter'    : [],
    'Halogen'     : [], 'Stash'     : [],
    'Seer'        : [], 'Koivisto'  : [],
    'Drofa'       : [], 'Bit-Genie' : [],
    'Berserk'     : [], 'Zahak'     : [],
    'BlackMarlin' : [],
};

ERRORS = {
    'cutechess'    : 'Unable to fetch Cutechess location and download it!',
    'configure'    : 'Unable to fetch and determine acceptable workloads!',
    'request'      : 'Unable to reach server for workload request!',
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
OSNAME    = '%s %s' % (platform.system(), platform.release())
DEBUG     = True

def locate_utility(util, force_exit=True, report_error=True):

    try:
        process = Popen([util, '--version'], stdout=PIPE)
        stdout, stderr = process.communicate()

        ver = re.search('[0-9]+.[0-9]+.[0-9]+', str(stdout))
        print('Located %s (%s)' % (util, ver.group()))
        return True

    except Exception:
        if report_error:
            print('[Error] Unable to locate %s' % (util))
        if force_exit:
            sys.exit()
        return False

def check_for_utilities():

    print('\nScanning For Basic Utilities...')
    for utility in ['gcc', 'make']:
        locate_utility(utility)


def init_client(arguments):

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

def download_file(source, outname, post_data=None):

    arguments = { 'stream' : True, 'timeout' : TIMEOUT_ERROR }
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

    command = 'make %s=%s EXE=%s -j%s' % (
        ['CC', 'CXX']['++' in COMPILERS[engine]], COMPILERS[engine], engine, arguments.threads)

    if engine in CUSTOM_SETTINGS:
        command += ' '.join(CUSTOM_SETTINGS[engine])

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

def run_bench(engine, outqueue):

    try:
        # Launch the engine and parse output for statistics
        process = Popen(['./' + engine, 'bench'], stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
        outqueue.put(parse_bench_output(stdout))
    except Exception: outqueue.put((0, 0))

def scale_time_control(workload, nps):

    # Searching for X/Y+Z time controls
    pattern = '(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
    results = re.search(pattern, workload['test']['timecontrol'])
    moves, base, inc = results.group('moves', 'base', 'inc')

    # Strip the trailing and leading symbols
    moves = None if moves == '' else moves.rstrip('/')
    inc   = 0.0  if inc   is None else inc.lstrip('+')

    # Scale the time based on this machines NPS
    base = float(base) * int(workload['test']['nps']) / nps
    inc  = float(inc ) * int(workload['test']['nps']) / nps

    # Format the time control for cutechess
    if moves is None: return '%.2f+%.2f' % (base, inc)
    return '%d/%.2f+%.2f' % (int(moves), base, inc)

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

    print ('\nScanning for Compilers...')

    # Fetch { Engine -> Compilers } from the server
    target = url_join(arguments.server, 'clientGetBuildInfo')
    data   = requests.get(target, timeout=TIMEOUT_HTTP).json()

    def get_version(compiler):

        # Try to execute the compiler from the command line
        # First with `--version`, and again with just `version`

        try:
            process = Popen([compiler, '--version'], stdout=PIPE, stderr=PIPE)
            stdout = process.communicate()[0].decode('utf-8')
            return re.search(r'[0-9]+\.[0-9]+\.[0-9]+', stdout).group()

        except:
            process = Popen([compiler, 'version'], stdout=PIPE, stderr=PIPE)
            stdout = process.communicate()[0].decode('utf-8')
            return re.search(r'[0-9]+\.[0-9]+\.[0-9]+', stdout).group()

    # For each engine, attempt to find a valid compiler
    for engine, build_info in data.items():
        for compiler in build_info['compilers']:

            # Compilers may require a specific version
            if '>=' in compiler:
                compiler, version = compiler.split('>=')
                version = tuple(map(int, version.split('.')))
            else: version = (0, 0, 0)

            try: match = get_version(compiler)
            except: continue # Unable to execute compiler

            # Compiler version was sufficient
            if tuple(map(int, match.split('.'))) >= version:
                print('%14s | %s (%s)' % (engine, compiler, match))
                COMPILERS[engine] = compiler
                break

    # Report missing engines in case the User is not expecting it
    for engine in filter(lambda x: x not in COMPILERS, data):
        compiler = data[engine]['compilers']
        print('%14s | Missing %s' % (engine, compiler))

    print('\nScanning for CPU Flags...')

    # Use GCC -march=native to find CPU info
    stdout, stderr = Popen(
        'echo | gcc -march=native -E -dM -',
        stdout=PIPE, shell=True
    ).communicate()

    # Check for each requested flag using the gcc dump
    desired = [info['cpuflags'] for engine, info in data.items()]
    flags   = set(sum(desired, [])) # Trick to flatten the list
    actual  = set(f for f in flags if '__%s__ 1' % (f) in str(stdout))

    # Report and save to global configuration
    print('     Found |', ' '.join(list(actual)))
    print('   Missing |', ' '.join(list(flags - actual)))
    COMPILERS['cpuflags'] = ' '.join(list(actual))

@try_until_success(mesg=ERRORS['request'])
def server_request_workload(arguments):

    print('\nRequesting Workload from Server...')

    machine_id = 'None'
    if os.path.isfile('machine.txt'):
        with open('machine.txt') as fin:
            machine_id = fin.readlines()[0]

    if machine_id == 'None':
        print('[NOTE] This machine is currently unregistered')

    supported  = ' '.join(COMPILERS.keys() - ['cpuflags'])

    payload = {
        'username'   : arguments.username, 'threads'    : arguments.threads,
        'password'   : arguments.password, 'osname'     : OSNAME,
        'machineid'  : machine_id,         'syzygy_wdl' : bool(SYZYGY_WDL_PATH),
        'supported'  : supported,          'cpuflags'   : COMPILERS['cpuflags'],
        'version'    : CLIENT_VERSION
    }

    target = url_join(arguments.server, 'clientGetWorkload')
    return requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

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
        print('[Note] Server Has No Work')
        if not FLEET_MODE: time.sleep(TIMEOUT_WORKLOAD)
        return False

    # Bad login, kill the worker since all requests will fail
    if raw_text == 'Bad Credentials':
        print('[Error] Invalid Login Credentials')
        sys.exit()

    # Bad machine, mostly meaningless but note it
    if raw_text == 'Bad Machine':
        print('[Note] Replacing Invalid Machine Id')
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

    dev_network  = download_network_weights(arguments, workload, 'dev')
    base_network = download_network_weights(arguments, workload, 'base')

    dev_name  = download_engine(arguments, workload, 'dev', dev_network)
    base_name = download_engine(arguments, workload, 'base', base_network)
    if dev_name == None or base_name == None: return

    dev_bench,  dev_nps  = run_benchmarks(arguments, workload, 'dev', dev_name)
    base_bench, base_nps = run_benchmarks(arguments, workload, 'base', base_name)

    dev_status  = verify_benchmarks(arguments, workload, 'dev', dev_bench)
    base_status = verify_benchmarks(arguments, workload, 'base', base_bench)

    if not dev_status or not base_status: return
    server_report_nps(arguments, workload, dev_nps, base_nps)
    download_opening_book(arguments, workload)

    avg_nps = (dev_nps + base_nps) // 2
    concurrency, update_interval, command = build_cutechess_command(
        arguments, workload, dev_name, base_name, avg_nps)

    run_and_parse_cutechess(arguments, workload, concurrency, update_interval, command)

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

    if arguments.proxy: source = 'https://ghproxy.com/' + source

    pattern = '\nEngine: [%s] %s\nCommit: %s'
    print(pattern % (engine, branch_name, commit_sha.upper()))

    # Naming as Engine-SHA256[:8]-NETSHA256[:8]
    final_name = '%s-%s' % (engine, commit_sha.upper()[:8])
    if network: final_name += '-%s' % (network[-8:])

    # Check to see if we already have the final binary
    final_path = os.path.join('Engines', final_name)
    if os.path.isfile(final_path): return final_name
    if os.path.isfile(final_path + '.exe'): return final_name + '.exe'

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
    command = make_command(arguments, engine, src_path, network)
    process = Popen(command, cwd=src_path, stdout=PIPE, stderr=STDOUT)
    compiler_output = process.communicate()[0].decode('utf-8')
    print (compiler_output)

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

    # Notify the server if the build failed
    server_report_build_fail(arguments, workload, branch, compiler_output)
    return None

def run_benchmarks(arguments, workload, branch, engine):

    cores = int(arguments.threads)
    queue = multiprocessing.Queue()
    name  = workload['test'][branch]['name']
    print('\nRunning %dx Benchmarks for %s' % (cores, name))

    for ii in range(cores):
        args = (os.path.join('Engines', engine), queue,)
        proc = multiprocessing.Process(target=run_bench, args=args)
        proc.start()

    nps, bench = list(zip(*[queue.get() for ii in range(cores)]))
    if len(set(bench)) > 1: return (0, 0) # Flag an error

    print('Bench for %s is %d' % (name, bench[0]))
    print('Speed for %s is %d' % (name, sum(nps) // cores))
    return bench[0], sum(nps) // cores

def verify_benchmarks(arguments, workload, branch, bench):
    if bench != int(workload['test'][branch]['bench']):
        server_report_bad_bench(arguments, workload, branch, bench)
    return bench == int(workload['test'][branch]['bench'])

def build_cutechess_command(arguments, workload, dev_name, base_name, nps):

    dev_options  = workload['test']['dev' ]['options']
    base_options = workload['test']['base']['options']

    dev_threads  = int(re.search('(?<=Threads=)\d*', dev_options ).group())
    base_threads = int(re.search('(?<=Threads=)\d*', base_options).group())

    if SYZYGY_WDL_PATH and workload['test']['syzygy_wdl'] != 'DISABLED':
        path = SYZYGY_WDL_PATH.replace('\\', '\\\\')
        dev_options  += ' SyzygyPath=%s' % (path)
        base_options += ' SyzygyPath=%s' % (path)

    dev_options  = ' option.'.join([''] +  dev_options.split())
    base_options = ' option.'.join([''] + base_options.split())

    book_name = workload['test']['book']['name']
    variant   = ['standard', 'fischerandom']['FRC' in book_name.upper()]

    flags  = '-repeat -recover -resign %s -draw %s '
    flags += '-srand %d -variant %s -concurrency %d -games %d '
    flags += '-engine dir=Engines/ cmd=./%s proto=uci tc=%s%s name=%s '
    flags += '-engine dir=Engines/ cmd=./%s proto=uci tc=%s%s name=%s '
    flags += '-openings file=Books/%s format=%s order=random plies=16 '
    flags += '-pgnout PGNs/%s_vs_%s '

    if SYZYGY_WDL_PATH and workload['test']['syzygy_adj'] != 'DISABLED':
        flags += '-tb %s' % (SYZYGY_WDL_PATH.replace('\\', '\\\\'))

    concurrency = int(arguments.threads) // max(dev_threads, base_threads)
    update_interval = 8 if max(dev_threads, base_threads) == 1 else 1

    games = int(concurrency * BASE_GAMES_PER_CORE)
    games = max(8, concurrency * 2, games - (games % (2 * concurrency)))

    time_control = scale_time_control(workload, nps)

    args = (
        'movecount=3 score=400', 'movenumber=40 movecount=8 score=10',
        int(time.time()), variant, concurrency, games,
        dev_name, time_control, dev_options, dev_name.rstrip('.exe'),
        base_name, time_control, base_options, base_name.rstrip('.exe'),
        book_name, book_name.split('.')[-1],
        dev_name.rstrip('.exe'), base_name.rstrip('.exe')
    )

    if IS_LINUX:
        return concurrency, update_interval, './cutechess-ob ' + flags % (args)
    return concurrency, update_interval, 'cutechess-ob.exe ' + flags % (args)

def run_and_parse_cutechess(arguments, workload, concurrency, update_interval, command):

    print('\nLaunching Cutechess...\n%s\n' % (command))
    cutechess = Popen(command.split(), stdout=PIPE)

    crashes = timelosses = 0
    score   = [0, 0, 0]; sent = [0, 0, 0] # WLD
    errors  = ['on time', 'disconnects', 'connection stalls', 'illegal']

    while True:

        # Read each line of output until the pipe closes
        line = cutechess.stdout.readline().strip().decode('ascii')
        if line != '': print(line)
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
        if ((sum(score) - sum(sent)) % update_interval != 0): continue

        # Report to the server but allow failed reports to delay
        wld = [score[ii] - sent[ii] for ii in range(3)]
        stats = wld + [crashes, timelosses]
        status = server_report_results(arguments, workload, stats)

        # Check for the task being aborted
        if status.upper() == 'STOP':
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
    p.add_argument('-U', '--username', help=help_user  , required=req_user)
    p.add_argument('-P', '--password', help=help_pass  , required=req_pass)
    p.add_argument('-S', '--server'  , help='Webserver', required=True)
    p.add_argument('-T', '--threads' , help='Threads'  , required=True)
    p.add_argument('--syzygy', help='Syzygy WDL'  , required=False)
    p.add_argument('--fleet' , help='Fleet Mode'  , action='store_true')
    p.add_argument('--proxy' , help='Github Proxy', action='store_true')
    arguments = p.parse_args()

    if arguments.username is None:
        arguments.username = os.environ['OPENBENCH_USERNAME']

    if arguments.password is None:
        arguments.password = os.environ['OPENBENCH_PASSWORD']

    if arguments.syzygy is not None:
        SYZYGY_WDL_PATH = arguments.syzygy

    if arguments.fleet:
        FLEET_MODE = True

    check_for_utilities()
    init_client(arguments)
    server_download_cutechess(arguments)
    server_configure_worker(arguments)

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
