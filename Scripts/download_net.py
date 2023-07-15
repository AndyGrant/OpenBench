#!/bin/python3

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

def url_join(*args):
    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + '/'

def download_network(username, password, server, engine, name):

    print ('Downloading %s for %s...' % (name, engine))

    target  = url_join(server, 'clientGetNetwork', engine, name)
    payload = { 'username' : username, 'password' : password }
    request = requests.post(data=payload, url=target)

    with open(name, 'wb') as fout:
        for chunk in request.iter_content(chunk_size=1024):
            if chunk: fout.write(chunk)
        fout.flush()

if __name__ == '__main__':

    # We can use ENV variables for Username, Password, and Server
    req_user   = required=('OPENBENCH_USERNAME' not in os.environ)
    req_pass   = required=('OPENBENCH_PASSWORD' not in os.environ)
    req_server = required=('OPENBENCH_SERVER' not in os.environ)

    # For clarity, seperate out this help text
    help_user   = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass   = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'
    help_server = '  Server. May also be passed as OPENBENCH_SERVER   environment variable'

    # Parse all arguments, all of which must exist in some form
    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help=help_user    , required=req_user  )
    p.add_argument('-P', '--password', help=help_pass    , required=req_pass  )
    p.add_argument('-S', '--server'  , help=help_server  , required=req_server)
    p.add_argument('-E', '--engine'  , help='Engine'     , required=True      )
    p.add_argument('-N', '--network' , help='Name or Sha', required=True      )
    args = p.parse_args()

    # Fallback on ENV variables for Username, Password, and Server
    args.username = args.username if args.username else os.environ['OPENBENCH_USERNAME']
    args.password = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
    args.server   = args.server   if args.server   else os.environ['OPENBENCH_SERVER'  ]

    download_network(args.username, args.password, args.server, args.engine, args.network)
