#!/usr/bin/python3

import argparse, hashlib, os, requests

OPENBENCH_SERVER = 'http://chess.grantnet.us'

def download_network(username, password, sha256):

    print ('Downloading %s...' % (sha256))

    # Check if we already have the Network file by looking at SHA256
    if os.path.isfile(sha256):
        with open(sha256, 'rb') as network:
            if sha256 == hashlib.sha256(network.read()).hexdigest()[:8].upper():
                return

    target = '%s/clientGetNetwork/%s/' % (OPENBENCH_SERVER, sha256)
    payload = { 'username' : username, 'password' : password }
    request = requests.post(data=payload, url=target)

    with open(sha256, 'wb') as fout:
        for chunk in request.iter_content(chunk_size=1024):
            if chunk: fout.write(chunk)
        fout.flush()

    with open(sha256, 'rb') as network:
        if sha256 != hashlib.sha256(network.read()).hexdigest()[:8].upper():
            print ('Failed to Download...')

if __name__ == '__main__':

    req_user  = required=('OPENBENCH_USERNAME' not in os.environ)
    req_pass  = required=('OPENBENCH_PASSWORD' not in os.environ)
    help_user = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'

    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help=help_user       , required=req_user)
    p.add_argument('-P', '--password', help=help_pass       , required=req_pass)
    p.add_argument('-N', '--network',  help='Network SHA256', required=True)
    arguments = p.parse_args()

    if arguments.username is None: arguments.username = os.environ['OPENBENCH_USERNAME']
    if arguments.password is None: arguments.password = os.environ['OPENBENCH_PASSWORD']

    download_network(arguments.username, arguments.password, arguments.network)
