import argparse
import hashlib
import multiprocessing
import os
import re
import requests
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from bench_engine import run_benchmark
from OpenBench.config import OPENBENCH_CONFIG

USE_OLD_BINARIES   = True
OPENBENCH_USERNAME = None
OPENBENCH_PASSWORD = None
OPENBENCH_SERVER   = 'http://chess.grantnet.us'
BENCHMARK_THREADS  = None
BENCHMARK_SETS     = None

def download_network(engine, sha256):

    if not os.path.isdir('Networks'):
        os.mkdir('Networks')

    if not os.path.isfile('Networks/%s' % (sha256)):

        print ('Downloading %s for %s...' % (sha256, engine))

        target = '%s/clientGetNetwork/%s/' % (OPENBENCH_SERVER, sha256)
        payload = { 'username' : OPENBENCH_USERNAME, 'password' : OPENBENCH_PASSWORD }
        request = requests.post(data=payload, url=target)

        with open('Networks/%s' % (sha256), 'wb') as fout:
            for chunk in request.iter_content(chunk_size=1024):
                if chunk: fout.write(chunk)
            fout.flush()

    with open('Networks/%s' % (sha256), 'rb') as network:
        assert sha256 == hashlib.sha256(network.read()).hexdigest()[:8].upper()

def download_default_networks():

    target = '%s/networks/' % (OPENBENCH_SERVER)
    information = requests.get(url=target)

    pattern = r'class="fas fa-star">.*?<a href="/networks/(?P<eng>.*?)/".*?<a href="/networks/download/(?P<sha>.{8})'
    default_networks = list(re.findall(pattern, information.text))

    for engine, network in default_networks:
        download_network(engine, network)

    return { engine : network for engine, network in default_networks }

def update_repositories():

    if not os.path.isdir('Repositories'):
        os.mkdir('Repositories')

    for engine, config in OPENBENCH_CONFIG['engines'].items():

        if not os.path.isdir('Repositories/' + config['source'].split('/')[-1]):
            os.system('cd Repositories && git clone %s && cd ../' % (config['source']))

        if not USE_OLD_BINARIES:
            os.system('cd Repositories/%s && git pull && cd ../../' % config['source'].split('/')[-1])

def build_engine(engine, config, defaults):

    git_path   = 'Repositories/' + config['source'].split('/')[-1]
    base_path  = os.path.dirname(os.path.realpath(__file__))
    build_path = os.path.join(base_path, git_path, config['build']['path'])

    command = 'make -j EXE=%s' % (engine)
    if engine in defaults:
        command += ' EVALFILE=%s' % (os.path.join(base_path, 'Networks', defaults[engine]).replace('\\', '/'))

    print ('=' * 120)
    print ('Attempting to build %s...' % (engine))
    subprocess.Popen(command.split(), cwd=build_path).wait()

    if os.path.isfile(os.path.join(build_path, engine)):
        os.rename(os.path.join(build_path, engine), os.path.join('Binaries', engine))
        print ('Succesfully built %s' % (engine))

    if os.path.isfile(os.path.join(build_path, engine + '.exe')):
        os.rename(os.path.join(build_path, engine + '.exe'), os.path.join('Binaries', engine))
        print ('Succesfully built %s' % (engine))

    print ('=' * 120)
    print ()

def build_all_engines():

    update_repositories()
    defaults = download_default_networks()

    if not os.path.isdir('Binaries'):
        os.mkdir('Binaries')

    for engine, config in OPENBENCH_CONFIG['engines'].items():
        if USE_OLD_BINARIES and os.path.isfile('Binaries/' + engine):
            continue

        build_engine(engine, config, defaults)

def bench_built_engines():

    for engine in sorted(os.listdir('Binaries')):
        nps = run_benchmark('./Binaries/%s' % (engine), BENCHMARK_THREADS, BENCHMARK_SETS)
        print ('%-15s | %d' % (engine, nps))

if __name__ == '__main__':

    req_user  = required=('OPENBENCH_USERNAME' not in os.environ)
    req_pass  = required=('OPENBENCH_PASSWORD' not in os.environ)
    help_user = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'

    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help=help_user, required=req_user)
    p.add_argument('-P', '--password', help=help_pass, required=req_pass)
    p.add_argument('-T', '--threads' , help='Concurrent Benchmarks',  required=True)
    p.add_argument('-S', '--sets'    , help='Benchmark Sample Count', required=True)
    p.add_argument('-R', '--rebuild' , help='Rebuild Binaries',       action='store_true')
    arguments = p.parse_args()

    USE_OLD_BINARIES   = not arguments.rebuild
    OPENBENCH_USERNAME = arguments.username
    OPENBENCH_PASSWORD = arguments.password
    BENCHMARK_THREADS  = int(arguments.threads)
    BENCHMARK_SETS     = int(arguments.sets)

    if arguments.username is None: OPENBENCH_USERNAME = os.environ['OPENBENCH_USERNAME']
    if arguments.password is None: OPENBENCH_PASSWORD = os.environ['OPENBENCH_PASSWORD']

    build_all_engines()
    bench_built_engines()