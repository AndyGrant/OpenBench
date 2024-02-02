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
import os
import sys

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(PARENT))

from Client.bench import run_benchmark

if __name__ == '__main__':

    p = argparse.ArgumentParser()
    p.add_argument('-E', '--engine'  , help='Binary Name',                  required=True)
    p.add_argument('-N', '--network' , help='Networks for Private Engines', required=False)
    p.add_argument('-T', '--threads' , help='Concurrent Benchmarks',        required=True, type=int)
    p.add_argument('-S', '--sets'    , help='Benchmark Sample Count',       required=True, type=int)
    args = p.parse_args()

    private = args.network != None
    speed, bench = run_benchmark(args.engine, args.network, private, args.threads, args.sets)

    print('Bench for %s is %d' % (args.engine, bench))
    print('Speed for %s is %d' % (args.engine, speed))
