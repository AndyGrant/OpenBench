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
import io
import os
import re
import tarfile

def pgn_iterator(content):

    def pgn_header_list(lines):
        return { f.split()[0][1:] : re.search(r'"([^"]*)"', f).group(1) for f in lines }

    data = io.StringIO(content.decode('utf-8'))

    while True:

        headers   = pgn_header_list(iter(lambda: data.readline().rstrip(), ''))
        move_text = ' '.join(iter(lambda: data.readline().rstrip(), ''))

        if not headers or not move_text:
            break

        yield (headers, move_text)

def process_content(content, data):

    comment_regex = r'{(book|[+-]?M?\d+(?:\.\d+)? \d+/\d+ \d+ \d+)[^}]*}'

    for (headers, move_text) in pgn_iterator(content):

        white = headers['White'].split('-')[-1]
        black = headers['Black'].split('-')[-1]
        white_stm = 'FEN' not in headers or headers['FEN'].split()[1] == 'w'

        for engine in (white, black):
            if engine not in data:
                data[engine] = { 'nodes' : 0, 'time' : 0 }

        for x in re.compile(comment_regex).findall(move_text):

            if len(tokens := x.split()) == 4:
                data[white if white_stm else black]['time']  += int(tokens[2])
                data[white if white_stm else black]['nodes'] += int(tokens[3])

            white_stm = not white_stm

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help='Path to the OpenBench pgn archive')
    args = parser.parse_args()

    data = {}
    with tarfile.open(args.filename, 'r') as tar:
        for member in filter(lambda x: x.isfile(), tar.getmembers()):
            if file := tar.extractfile(member):
                process_content(bz2.decompress(file.read()), data)

    dev_nps  = 1000 * data['dev' ]['nodes'] / data['dev' ]['time']
    base_nps = 1000 * data['base']['nodes'] / data['base']['time']

    print ('Dev  : %d nps' % (int(dev_nps)))
    print ('Base : %d nps' % (int(base_nps)))
    print ('Gain : %.3f%%' % (100.0 * dev_nps / base_nps - 100.0))
