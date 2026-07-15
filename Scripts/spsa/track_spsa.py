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
import json
import os
import sys
import time
import traceback

# Needed to include from ../../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir)
sys.path.append(os.path.abspath(os.path.join(PARENT, 'Client')))

from utils import *

def fetch_snapshot(args):

    # /info returns { 'info' : {...} } as JSON
    request = credentialed_request(args.server, args.username, args.password, 'api/workload/%d/info' % (args.spsa))
    info    = request.json()['info']

    # /digest returns a CSV table as text/plain
    request = credentialed_request(args.server, args.username, args.password, 'api/spsa/%d/digest' % (args.spsa))
    digest  = request.text

    # Package the moment in time together with both payloads
    return (datetime.datetime.now().isoformat(), info, digest)

if __name__ == '__main__':

    # Use track_spsa.py's path as the base pathway
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # credentialed_cmdline_args() adds --username, --password, and --server
    parser = argparse.ArgumentParser()
    parser.add_argument('--spsa',     help='SPSA Workload Id to track', required=True, type=int)
    parser.add_argument('--interval', help='Polling interval in minutes', default=2, type=float)
    args = credentialed_cmdline_args(parser)

    # All snapshots for a given SPSA are appended to a single log file
    log_path = 'spsa.%d.log' % (args.spsa)

    while True:

        try:
            snapshot = fetch_snapshot(args)
            with open(log_path, 'a') as fout:
                fout.write(json.dumps(snapshot) + '\n')
            print ('[%s] Logged snapshot for SPSA %d' % (snapshot[0], args.spsa))

        except Exception:
            print ('[%s] Failed to fetch snapshot for SPSA %d' % (datetime.datetime.now().isoformat(), args.spsa))
            traceback.print_exc()

        time.sleep(args.interval * 60)
