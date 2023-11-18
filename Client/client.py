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
import importlib
import os
import requests
import shutil
import tempfile
import time
import traceback
import zipfile

class BadVersionException(Exception):
    def __init__(self, message='Wrong Client Version'):
        self.message = message
        super().__init__(self.message)

def url_join(*args):

    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + '/'

def try_forever(func, args, message, timeout=15):

    # Execute func(arg1, arg2, ...) until success

    while True:

        try:
            return func(*args)

        except BadVersionException:
            raise BadVersionException()

        except Exception as exception:
            print ('\n\n' + message)
            print ('[Note] Sleeping for %d seconds' % (timeout))
            print ('[Note] Traceback:')
            traceback.print_exc()
            print ()

        time.sleep(timeout)


def has_worker():
    try:
        import worker
        return True
    except ImportError:
        return False

def parse_arguments():

    # We can use ENV variables for the Username, Passwords, and Servers
    req_user   = 'OPENBENCH_USERNAME' not in os.environ
    req_pass   = 'OPENBENCH_PASSWORD' not in os.environ
    req_server = 'OPENBENCH_SERVER'   not in os.environ

    help_user   = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass   = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'
    help_server = 'Server URL. May also be passed as OPENBENCH_SERVER environment variable'

    # Create and parse all arguments into a raw format
    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username'   , help=help_user           , required=req_user  )
    p.add_argument('-P', '--password'   , help=help_pass           , required=req_pass  )
    p.add_argument('-S', '--server'     , help=help_server         , required=req_server)
    p.add_argument('-T', '--threads'    , help='Total Threads'     , required=True      )
    p.add_argument('-N', '--nsockets'   , help='Number of Sockets' , required=True      )
    p.add_argument('-I', '--identity'   , help='Machine pseudonym' , required=False     )
    p.add_argument(      '--syzygy'     , help='Syzygy WDL'        , required=False     )
    p.add_argument(      '--fleet'      , help='Fleet Mode'        , action='store_true')
    p.add_argument(      '--clean'      , help='Force New Client'  , action='store_true')

    args = p.parse_args()

    args.username = args.username if args.username else os.environ['OPENBENCH_USERNAME']
    args.password = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
    args.server   = args.server   if args.server   else os.environ['OPENBENCH_SERVER'  ]

    return args

def download_client_files(args):

    try: # Reponse may contain an error header for invalid credentials
        payload     = { 'username' : args.username, 'password' : args.password }
        target      = url_join(args.server, 'clientVersionRef')
        version_ref = requests.post(target, data=payload).json()

    except:
        raise Exception('Unable to retrieve Client Version from OpenBench server')

    try: # Download the entire .zip for the branch / tag / commit ref
        repo_url = version_ref['client_repo_url']
        repo_ref = version_ref['client_repo_ref']
        response = requests.get(url_join(repo_url, 'archive', '%s.zip' % (repo_ref)))
        assert response.status_code == 200

    except:
        raise Exception('Unable to retrieve .zip archive from Github')

    try: # Save to .zip, extract, and copy contents

        # Save response content to a temp file
        with tempfile.TemporaryFile() as temp_zip_file:
            temp_zip_file.write(response.content)

            # Extract the zip with a temp file
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(temp_zip_file) as zip_file:
                    zip_file.extractall(temp_dir)

                # Copy all files except client.py
                client_dir = os.path.join(temp_dir, 'OpenBench-%s' % (repo_ref), 'Client')
                for root, dirs, files in os.walk(client_dir):
                    for file in files:
                        if file != 'client.py':
                            shutil.copy2(os.path.join(root, file), os.path.join(os.getcwd(), file))

    except:
        raise Exception('Unable to extract .zip archive contents')


if __name__ == '__main__':

    # Use client.py's path as the base pathway
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    args = parse_arguments()

    if args.clean or not has_worker():
        print ('[NOTE] Downloading Client...')
        try_forever(download_client_files, [args], 'Failed to download Client files')

    from client import BadVersionException

    while True:

        try:
            import worker
            importlib.reload(worker)
            worker.run_openbench_worker(args)

        except BadVersionException:
            print ('[NOTE] Downloading newer version of Client...')
            try_forever(download_client_files, [args], 'Failed to download Client files')

        except KeyboardInterrupt:
            break
