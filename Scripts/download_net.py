import argparse
import hashlib
import os
import requests

OPENBENCH_USERNAME = None
OPENBENCH_PASSWORD = None
OPENBENCH_SERVER   = 'http://chess.grantnet.us'

def download_network(engine, sha256):

    if not os.path.isfile(sha256):

        print ('Downloading %s for %s...' % (sha256, engine))

        target = '%s/clientGetNetwork/%s/' % (OPENBENCH_SERVER, sha256)
        payload = { 'username' : OPENBENCH_USERNAME, 'password' : OPENBENCH_PASSWORD }
        request = requests.post(data=payload, url=target)

        with open(sha256, 'wb') as fout:
            for chunk in request.iter_content(chunk_size=1024):
                if chunk: fout.write(chunk)
            fout.flush()

    with open(sha256, 'rb') as network:
        assert sha256 == hashlib.sha256(network.read()).hexdigest()[:8].upper()

if __name__ == '__main__':

    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help='OpenBench Username', required=True)
    p.add_argument('-P', '--password', help='OpenBench Password', required=True)
    p.add_argument('-E', '--engine',   help='Engine',             required=True)
    p.add_argument('-N', '--network',  help='Network SHA256',     required=True)
    arguments = p.parse_args()

    OPENBENCH_USERNAME = arguments.username
    OPENBENCH_PASSWORD = arguments.password

    download_network(arguments.engine, arguments.network)
