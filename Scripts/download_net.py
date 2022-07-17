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

    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help='OpenBench Username', required=True)
    p.add_argument('-P', '--password', help='OpenBench Password', required=True)
    p.add_argument('-N', '--network',  help='Network SHA256',     required=True)
    args = p.parse_args()

    download_network(args.username, args.password, args.network)
