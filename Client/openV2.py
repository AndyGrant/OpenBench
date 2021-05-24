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

from subprocess import PIPE, Popen

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

TIMEOUT_HTTP        = 30   # Timeout in seconds for HTTP requests
TIMEOUT_ERROR       = 30   # Timeout in seconds when any errors are thrown
TIMEOUT_WORKLOAD    = 60   # Timeout in seconds between workload requests

DELETE_OLD_ENGINES  = 24   # Number of hours until deleting Engines
DELETE_OLD_NETWORKS = 720  # Number of hours until deleting Networks
DELETE_OLD_PGNS     = None # Number of hours until deleting PGNs

SYZYGY_WDL_PATH     = 'C:\\Users\\14438\\Desktop\\Syzygy\\' # Pathway to WDL Syzygy Tables
SYZYGY_DTZ_PATH     = 'C:\\Users\\14438\\Desktop\\Syzygy\\' # Pathway to DTZ Syzygy Tables
BASE_GAMES_PER_CORE = 32   # Typical games played per-thread

CUSTOM_SETTINGS = {
    'Ethereal'  : [], 'Laser'     : [],
    'Weiss'     : [], 'Demolito'  : [],
    'Rubichess' : [], 'FabChess'  : [],
    'Igel'      : [], 'Winter'    : [],
    'Halogen'   : [], 'Stash'     : [],
};

ERRORS = {
    'cutechess' : 'Unable to fetch Cutechess location and download it.',
    'configure' : 'Unable to fetch engine data and find acceptable workloads',
    'request'   : 'Unable to reach server for workload request.',
}

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   Setting up the Client. Build the OpenBench file structure, check for    #
#   Syzygy Tables for both WDL and DTZ, download a static Cutechess binary, #
#   and determine what engines we are able to compile by asking the server. #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Differentiate Windows and Linux systems
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX   = platform.system() != 'Windows'

COMPILERS = {} # Compiler for each Engine, + CPU Flags
OSNAME    = '%s %s' % (platform.system(), platform.release())
DEBUG     = True


def check_for_utilities():

    def locate_utility(util):

        try:
            process = Popen([util, '--version'], stdout=PIPE)
            stdout, stderr = process.communicate()

            ver = re.search('[0-9]+.[0-9]+.[0-9]+', str(stdout))
            print ('Located %s (%s)' % (util.upper(), ver.group()))

        except OSError:
            print('[Error] Unable to locate %s' % (util.upper()))
            sys.exit()

    print('\nScanning For Basic Utilities...')
    for utility in ['gcc', 'make']:
        locate_utility(utility)

def init_client(arguments):

    # Use Client.py's path as the base pathway
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Ensure the folder structure for ease of coding
    for folder in ['Engines', 'Networks', 'Books', 'PGNs']:
        if not os.path.isdir(folder):
            os.mkdir(folder)

    # Verify all WDL/DTZ tables are present when told they are
    validate_syzygy_exists()

def cleanup_client():

    SECONDS_PER_DAY   = 60 * 60 * 24
    SECONDS_PER_MONTH = SECONDS_PER_DAY * 30

    file_age = lambda x: time.time() - os.path.getmtime(x)

    for file in os.listdir('Engines'):
        if file_age(os.path.join('Engines', file)) > SECONDS_PER_DAY:
            os.remove(os.path.join('Engines', file))

    for file in os.listdir('Networks'):
        if file_age(os.path.join('Networks', file)) > SECONDS_PER_MONTH:
            os.remove(os.path.join('Networks', file))

def validate_syzygy_exists():

    global SYZYGY_WDL_PATH, SYZYGY_DTZ_PATH

    print ('\nScanning for Syzygy Configuration...')

    for filename in tablebase_names():

        # Build the paths when the configuration enables Syzygy

        if SYZYGY_WDL_PATH:
            wdlpath = os.path.join(SYZYGY_WDL_PATH, filename + '.rtbw')

        if SYZYGY_DTZ_PATH:
            dtzpath = os.path.join(SYZYGY_DTZ_PATH, filename + '.rtbz')

        # Reset the configuration if the file is missing

        if SYZYGY_WDL_PATH and not os.path.isfile(wdlpath):
            print('Missing Syzygy File (%s)' % (filename + '.rtbw'))
            SYZYGY_WDL_PATH = None

        if SYZYGY_DTZ_PATH and not os.path.isfile(dtzpath):
            print('Missing Syzygy File (%s)' % (filename + '.rtbz'))
            SYZYGY_DTZ_PATH = None

    # Report final results, which may conflict with the original configuration

    if SYZYGY_WDL_PATH:
        print('Verified Syzygy WDL (%s)' % (SYZYGY_WDL_PATH))

    if SYZYGY_DTZ_PATH:
        print('Verified Syzygy DTZ (%s)' % (SYZYGY_DTZ_PATH))

def tablebase_names(K=6):

    letters = ['', 'Q', 'R', 'B', 'N', 'P']; candidates = []

    # Generate many potential K[] v K[], including all valid ones
    for N in range(1, K - 1):
        for lhs in combinations_with_replacement(letters, N):
            for rhs in combinations_with_replacement(letters, K - N - 2):
                candidates.append('K%svK%s' % (''.join(lhs), ''.join(rhs)))

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
                    print('[Error]', mesg); time.sleep(TIMEOUT_ERROR)
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

def make_command(arguments, engine, network_path):

    command = 'make CC=%s EXE=%s -j%s' % (
        COMPILERS[engine], engine, arguments.threads)

    if engine in CUSTOM_SETTINGS:
        command += ' '.join(CUSTOM_SETTINGS[engine])

    if network_path != None:
        network_path = network_path.replace('\\', '/')
        command += ' EVALFILE=%s' % (network_path)

    return command

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   All functions used to make requests to the OpenBench server. Workload   #
#   requests require Username and Password authentication. Afterwords, all  #
#   verification is done using a generated token assigned to each Workload. #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

@try_until_success(mesg=ERRORS['cutechess'])
def server_download_cutechess(arguments):

    print('\nScanning for Cutechess Binary...')

    if IS_WINDOWS and not os.path.isfile('cutechess.exe'):

        # Fetch the source location if we are missing the binary
        source = requests.get(
            url_join(arguments.server, 'clientGetFiles'),
            timeout=TIMEOUT_HTTP).content.decode('utf-8')

        # Windows workers simply need a static compile (64-bit)
        download_file(url_join(source, 'cutechess-windows.exe'), 'cutechess.exe')

    if IS_LINUX and not os.path.isfile('cutechess'):

        # Fetch the source location if we are missing the binary
        source = requests.get(
            url_join(arguments.server, 'clientGetFiles'),
            timeout=TIMEOUT_HTTP).content.decode('utf-8')

        # Linux workers need a static compile (64-bit) with execute permissions
        download_file(url_join(source, 'cutechess-linux'), 'cutechess')
        os.system('chmod 777 cutechess')

    print('Cutechess Binary found or obtained')

@try_until_success(mesg=ERRORS['configure'])
def server_configure_worker(arguments):

    print ('\nScanning for Compilers...')

    # Fetch { Engine -> Compilers } from the server
    target = url_join(arguments.server, 'clientGetBuildInfo')
    data   = requests.get(target, timeout=TIMEOUT_HTTP).json()

    for engine, build_info in data.items():
        for compiler in build_info['compilers']:

            # Compilers may require a specific version
            if '>=' in compiler:
                compiler, version = compiler.split('>=')
                version = tuple(map(int, version.split('.')))
            else: version = (0, 0, 0)

            # Try to execute the compiler from the command line
            try:
                process = Popen([compiler, '--version'], stdout=PIPE)
                stdout, stderr = process.communicate()
            except OSError: continue

            # Parse the version number reported by the compiler
            stdout = stdout.decode('utf-8')
            match  = re.search(r'[0-9]+\.[0-9]+\.[0-9]+', stdout).group()

            # Compiler version was sufficient
            if tuple(map(int, match.split('.'))) >= version:
                print('%10s :: %s (%s)' % (engine, compiler, match))
                COMPILERS[engine] = compiler
                break

    # Report missing engines in case the User is not expecting it
    for engine in filter(lambda x: x not in COMPILERS, data):
        compiler = data[engine]['compilers']
        print('%10s :: Missing %s' % (engine, compiler))

    print ('\nScanning for CPU Flags...')

    # Use GCC -march=native to find CPU info
    stdout, stderr = Popen(
        'echo | gcc -march=native -E -dM -'.split(),
        stdout=PIPE, shell=True
    ).communicate()

    # Check for each requested flag using the gcc dump
    desired = [info['cpuflags'] for engine, info in data.items()]
    flags   = set(sum(desired, [])) # Trick to flatten the list
    actual  = set(f for f in flags if '__%s__ 1' % (f) in str(stdout))

    # Report and save to global configuration
    print ('     Found ::', ' '.join(list(actual)))
    print ('   Missing ::', ' '.join(list(flags - actual)))
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
    has_syzygy = bool(SYZYGY_DTZ_PATH) and bool(SYZYGY_WDL_PATH)

    payload = {
        'username'   : arguments.username, 'threads'    : arguments.threads,
        'password'   : arguments.password, 'osname'     : OSNAME,
        'machineid'  : machine_id,         'syzygy_dtz' : str(has_syzygy),
        'supported'  : supported,          'cpuflags'   : COMPILERS['cpuflags'],
    }

    target = url_join(arguments.server, 'clientGetWorkload')
    return requests.post(target, data=payload, timeout=TIMEOUT_HTTP)

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
        time.sleep(TIMEOUT_WORKLOAD)
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

    # Final check that we may parse the workload JSON
    data = response.json()
    with open('machine.txt', 'w') as fout:
        fout.write(str(data['machine']['id']))

    # Log the start of the new workload
    engine = data['test']['engine']
    dev    = data['test']['dev'   ]['name']
    base   = data['test']['base'  ]['name']
    print ('Workload [%s] %s vs %s\n' % (engine, dev, base))

    return data

def complete_workload(arguments, workload):

    dev_network  = download_network_weights(arguments, workload, 'dev' )
    base_network = download_network_weights(arguments, workload, 'base')

    dev_engine  = download_engine(arguments, workload, 'dev',  dev_network )
    base_engine = download_engine(arguments, workload, 'base', base_network)

    dev_nps  = compute_engine_speed(arguments, workload, 'dev',  dev_engine )
    base_nps = compute_engine_speed(arguments, workload, 'base', base_engine)

    download_opening_book(workload)

def download_opening_book(workload):

    # Log our attempts to download and verify the book
    book_sha256 = workload['test']['book']['sha'   ]
    book_source = workload['test']['book']['source']
    book_name   = workload['test']['book']['name'  ]
    book_path   = os.path.join('Books', book_name)
    print ('\nFetching Opening Book [%s]' % (book_name))

    # Download file if we do not already have it
    if not os.path.isfile(book_path):
        download_file(book_source, book_name + '.zip')
        unzip_delete_file(book_name + '.zip', 'Books/')

    # Verify SHAs match with the server
    with open(book_path) as fin:
        content = fin.read().encode('utf-8')
        sha256 = hashlib.sha256(content).hexdigest()
    if book_sha256 != sha256: os.remove(book_path)

    # Log SHAs on every workload
    print ('Correct  SHA256 %s' % (book_sha256))
    print ('Download SHA256 %s' % (sha256))

    # We have to have the correct SHA to continue
    if book_sha256 != sha256:
        raise Exception('Invalid SHA for %s' % (book_name))

def download_network_weights(arguments, workload, branch):

    # Some tests may not use Neural Networks
    network_name = workload['test'][branch]['network']
    if not network_name or network_name == 'None': return None

    # Log that we are obtaining a Neural Network
    pattern = 'Fetching Neural Network [ %s, %-4s ]'
    print (pattern % (network_name, branch.upper()))

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

    pattern = '\nEngine: %s\nBranch: %s\nCommit: %s'
    print (pattern % (engine, branch_name, commit_sha.upper()))

    # Naming as SHA256[:16]-NETSHA256[:8]
    final_name = commit_sha.upper()[:16]
    if network: final_name += '-%s' % (network[-8:])

    # Check to see if we already have the final binary
    final_path = os.path.join('Engines', final_name)
    if os.path.isfile(final_path): return final_path

    # Download and unzip the source from Github
    download_file(source, '%s.zip' % (engine))
    unzip_delete_file('%s.zip' % (engine), 'tmp/')

    # Parse out paths to find the makefile location
    tokens     = source.split('/')
    unzip_name = '%s-%s' % (tokens[-3], tokens[-1].rstrip('.zip'))
    src_path   = os.path.join('tmp', unzip_name, *build_path.split('/'))

    # Build the engine and drop it into src_path
    print ('\nBuilding [%s]' % (final_path))
    rel_path = os.path.relpath(os.path.abspath(network), src_path)
    Popen(make_command(arguments, engine, rel_path), cwd=src_path).wait()
    output_name = os.path.join(src_path, engine)

    # Move the file to the final location ( Linux )
    if os.path.isfile(output_name):
        os.rename(output_name, final_path)

    # Move the file to the final location ( Windows )
    if os.path.isfile(output_name + '.exe'):
        os.rename(output_name + '.exe', final_path)

    # Cleanup the source code
    shutil.rmtree('tmp')

    # Relative location of final binary
    return final_path

def compute_engine_speed(arguments, workload, branch, engine):
    pass

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#                                                                           #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

if __name__ == '__main__':

    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help='Username' , required=True)
    p.add_argument('-P', '--password', help='Password' , required=True)
    p.add_argument('-S', '--server'  , help='Webserver', required=True)
    p.add_argument('-T', '--threads' , help='Threads'  , required=True)
    arguments = p.parse_args()

    check_for_utilities()
    init_client(arguments)
    server_download_cutechess(arguments)
    server_configure_worker(arguments)

    while True:
        cleanup_client()
        response = server_request_workload(arguments)
        workload = check_workload_response(arguments, response)
        if workload: complete_workload(arguments, workload)
        break