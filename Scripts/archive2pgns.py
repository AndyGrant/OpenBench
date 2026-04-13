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
import bz2
import collections
import concurrent.futures
import os
import tarfile

def process_archive(archive_path):

    output_path = archive_path[:-4]  # foo.pgn.tar -> foo.pgn
    window  = min(os.cpu_count() - 1, 15)
    pending = collections.deque()

    with tarfile.open(archive_path, 'r') as tar, \
         open(output_path, 'w') as out, \
         concurrent.futures.ThreadPoolExecutor(max_workers=window) as executor:

        for member in tar.getmembers():
            if not member.isfile():
                continue
            if file := tar.extractfile(member):
                if len(pending) >= window:
                    out.write(pending.popleft().result().decode('utf-8'))
                pending.append(executor.submit(bz2.decompress, file.read()))

        for future in pending:
            out.write(future.result().decode('utf-8'))

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('archives', nargs='+', help='Paths to .pgn.tar archives')
    args = parser.parse_args()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, os.cpu_count() // 16)) as executor:
        list(executor.map(process_archive, args.archives))
