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
import requests
import subprocess
import tempfile
import zipfile

class OpenBenchBuildFailedException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


def url_join(*args):

    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + '/'

def credentialed_cmdline_args(parser=None):

    # Adds username, password, and server to the ArgumentParser
    # Defers to the env variables for them, if not provided explicitly

    # Don't require inheritence from an existing ArgumentParser
    if not parser:
        parser = argparse.ArgumentParser()

    # We can use ENV variables for Username, Password, and Server
    req_user   = 'OPENBENCH_USERNAME' not in os.environ
    req_pass   = 'OPENBENCH_PASSWORD' not in os.environ
    req_server = 'OPENBENCH_SERVER'   not in os.environ

    # For clarity, seperate out this help text
    help_user   = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass   = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'
    help_server = '  Server. May also be passed as OPENBENCH_SERVER   environment variable'

    # Parse all arguments, all of which must exist in some form
    parser.add_argument('-U', '--username', help=help_user    , required=req_user  )
    parser.add_argument('-P', '--password', help=help_pass    , required=req_pass  )
    parser.add_argument('-S', '--server'  , help=help_server  , required=req_server)
    args = parser.parse_args()

    # Fallback on ENV variables for Username, Password, and Server
    args.username = args.username if args.username else os.environ['OPENBENCH_USERNAME']
    args.password = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
    args.server   = args.server   if args.server   else os.environ['OPENBENCH_SERVER'  ]

    return args

def credentialed_request(server, username, password, endpoint):

    target  = url_join(server, *endpoint.split('/'))
    payload = { 'username' : username, 'password' : password }

    return requests.post(data=payload, url=target)


def makefile_command(net_path, make_path, out_path, compiler, threads):

    # Build with EXE= to contol the output location
    command = ['make', 'EXE=%s' % (out_path)]

    # Build with CC/CXX= when using a custom compiler
    if compiler:
        comp_flag = ['CC', 'CXX']['++' in compiler]
        command  += ['%s=%s' % (comp_flag, compiler)]

    # Build with -jN, or just -j if threads is not explicit
    command += ['-j' if not threads else '-j%d' % (threads)]

    # Build with EVALFILE= to embed NNUE files
    if net_path:
        rel_net_path = os.path.relpath(os.path.abspath(net_path), make_path)
        command += ['EVALFILE=%s' % (rel_net_path.replace('\\', '/'))]

    return command


def download_network(server, username, password, engine, net_name, net_sha, net_path):

    print ('Fetching %s (%s) for %s' % (net_name, net_sha, engine))

    # Avoid redownloading Network files
    if not os.path.isfile(net_path):

        # Format the API request, including credentials
        endpoint = '/api/networks/%s/%s' % (engine, net_sha)
        request  = credentialed_request(server, username, password, endpoint)

        # Write the content out to the net_path in kb chunks
        with open(net_path, 'wb') as fout:
            for chunk in request.iter_content(chunk_size=1024):
                if chunk: fout.write(chunk)
            fout.flush()

    # Check for the first 8 characters of the sha256
    with open(net_path, 'rb') as network:
        sha256 = hashlib.sha256(network.read()).hexdigest()[:8].upper()

    # Verify the download and delete partial or corrupted ones
    if net_sha != sha256:
        os.remove(net_path)
        raise Exception('Invalid SHA for %s' % (network_sha))

def download_public_engine(engine, net_path, branch, source, make_path, out_path, compiler=None, threads=None):

    # Check for already having the binary ( Linux )
    if os.path.isfile(out_path):
        return out_path

    # Check for already having the binary ( Windows )
    if os.path.isfile('%s.exe' % (out_path)):
        return '%s.exe' % (out_path)

    # Work with temp files and directories until finished building
    with tempfile.TemporaryDirectory() as temp_dir:

        print('Building [%s-%s]' % (engine, branch))

        # Download the zip file from Github
        zip_path = os.path.join(temp_dir, '%s-%s' % (engine, branch))
        with open(zip_path, 'wb') as zip_file:
            zip_file.write(requests.get(source).content)

        # Unzip the engine to a directory called <engine>
        unzip_path = os.path.join(temp_dir, engine)
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            zip_file.extractall(unzip_path)

        # Rename the Root folder for ease of conventions
        unzip_root = os.path.join(unzip_path, os.listdir(unzip_path)[0])
        src_path   = os.path.join(unzip_path, '%s-%s' % (engine, branch))
        os.rename(unzip_root, src_path)

        # Prepare the MAKEFILE command
        make_path    = os.path.join(src_path, make_path)
        rel_out_path = os.path.relpath(os.path.abspath(out_path), make_path)
        make_cmd     = makefile_command(net_path, make_path, rel_out_path, compiler, threads)

        # Build the engine, which will produce a binary to the original out_path
        process     = subprocess.Popen(make_cmd, cwd=make_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        comp_output = process.communicate()[0].decode('utf-8')

    # Indicate where the true binary name ( Linux )
    if os.path.isfile(out_path):
        return out_path

    # Indicate where the true binary name ( Windows )
    if os.path.isfile('%s.exe' % (out_path)):
        return '%s.exe' % (out_path)

    # Someone should catch this, and possibly report it to the OpenBench server
    raise OpenBenchBuildFailedException(comp_output)



