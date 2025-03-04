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
import random

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(os.path.join(PARENT, 'Client')))

import genfens

if __name__ == '__main__':

    p = argparse.ArgumentParser()
    p.add_argument('--engine'     , help='Binary'                         , required=True )
    p.add_argument('--threads'    , help='Threads to generate with'       , required=True )
    p.add_argument('--count-per'  , help='Openings to generate per thread', required=True )
    p.add_argument('--book-path'  , help='Path to base Book, if any'      , default='None')
    p.add_argument('--extra'      , help='Extra genfens arguments'        , default=''    )
    p.add_argument('--network'    , help='Network, for Private Engines'   , default=None  )
    args = p.parse_args()

    # Same way that get_workload.py generates seeds
    seeds = [random.randint(0, 2**31 - 1) for x in range(int(args.threads))]

    with open('example_genfens.epd', 'w') as fout:

        genfen_args = {
            'N'       : int(args.count_per),
            'book'    : args.book_path,
            'seeds'   : seeds,
            'extra'   : args.extra,
            'private' : args.network != None,
            'engine'  : args.engine,
            'network' : args.network,
            'threads' : int(args.threads),
            'output'  : fout,
        }

        genfens.create_genfens_opening_book(genfen_args)
