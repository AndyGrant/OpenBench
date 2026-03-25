#!/usr/bin/env python3

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
import datetime
import os
import requests

def url_join(*args):
    # Join a set of URL paths while maintaining the correct format
    return '/'.join([f.lstrip('/').rstrip('/') for f in args]) + '/'


def delete_network(args, network):

    # Not from the requested author
    if network['author'] != args.author:
        return

    # Network name does not contain the critical text
    if args.contains and args.contains not in network['name']:
        return

    # Server won't let us delete such networks
    if network['default'] or network['was_default']:
        return

    # Network is more recent than we are willing to erase
    dt  = datetime.datetime.fromisoformat(network['created'])
    now = datetime.datetime.now(datetime.timezone.utc)
    if (now - dt).days < int(args.days):
        return

    if args.dry:
        print ('Dry run... deleting %s' % (network['name']))

    else:
        url  = url_join(args.server, 'api', 'networks', args.engine, network['name'], 'delete')
        data = { 'username' : args.username, 'password' : args.password }
        print (requests.post(url, data=data).json())

def delete_networks():

    # We can use ENV variables for Username, Password, and Server
    req_user   = required=('OPENBENCH_USERNAME' not in os.environ)
    req_pass   = required=('OPENBENCH_PASSWORD' not in os.environ)
    req_server = required=('OPENBENCH_SERVER' not in os.environ)

    help_user   = 'Username. May also be passed as OPENBENCH_USERNAME environment variable'
    help_pass   = 'Password. May also be passed as OPENBENCH_PASSWORD environment variable'
    help_server = '  Server. May also be passed as OPENBENCH_SERVER   environment variable'

    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help=help_user               , required=req_user  )
    p.add_argument('-P', '--password', help=help_pass               , required=req_pass  )
    p.add_argument('-S', '--server'  , help=help_server             , required=req_server)
    p.add_argument('-E', '--engine'  , help='Engine'                , required=True      )
    p.add_argument('-A', '--author'  , help='Network Author'        , required=True      )
    p.add_argument(      '--days'    , help='Delete iff N+ days old', required=True      )
    p.add_argument(      '--contains', help='Delete iif in name'    , required=False     )
    p.add_argument(      '--dry'     , help='Mock run'              , action='store_true')
    args = p.parse_args()

    # Fallback on ENV variables for Username, Password, and Server
    args.username = args.username if args.username else os.environ['OPENBENCH_USERNAME']
    args.password = args.password if args.password else os.environ['OPENBENCH_PASSWORD']
    args.server   = args.server   if args.server   else os.environ['OPENBENCH_SERVER'  ]

    url  = url_join(args.server, 'api', 'networks', args.engine)
    data = { 'username' : args.username, 'password' : args.password }
    nets = requests.post(url, data=data).json()['networks']

    for network in nets:
        delete_network(args, network)

if __name__ == '__main__':
    delete_networks()