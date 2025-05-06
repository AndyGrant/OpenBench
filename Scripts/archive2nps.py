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

def process_content(content, data, result_id, use_scale):

    comment_regex = r'{(book|[+-]?M?\d+(?:\.\d+)? \d+/\d+ \d+ \d+)[^}]*}'

    for (headers, move_text) in pgn_iterator(content):

        factor    = float(headers['ScaleFactor']) if use_scale else 1.00
        white     = headers['White'].split('-')[-1]
        black     = headers['Black'].split('-')[-1]
        white_stm = 'FEN' not in headers or headers['FEN'].split()[1] == 'w'

        # Setup to track stats per result-id
        if result_id not in data:
            data[result_id] = {}

        # Setup to track stats for this result-id
        for engine in (white, black):
            if engine not in data[result_id]:
                data[result_id][engine] = { 'nodes' : 0, 'time' : 0, 'games' : 0, 'ply' : 0 }
            data[result_id][engine]['games'] += 1

        for x in re.compile(comment_regex).findall(move_text):
            if len(tokens := x.split()) == 4:
                data[result_id][white if white_stm else black]['time']  += int(tokens[2]) / factor
                data[result_id][white if white_stm else black]['nodes'] += int(tokens[3])
                data[result_id][white if white_stm else black]['ply']   += 1
            white_stm = not white_stm

def report_verbose_stats(data):

    header = 'Result ID    Games      Dev       Base   '
    print (header)
    print ('-' * len(header))

    for result_id, stats in data.items():

        games = stats['dev']['games']

        dev_knps  = stats['dev']['nodes']  / stats['dev']['time']
        base_knps = stats['base']['nodes'] / stats['base']['time']

        print ('%5s %9d %7d knps %7d knps' % (result_id, games, dev_knps, base_knps))

def report_general_stats(data):

    games      = 0
    dev_nodes  = dev_time  = dev_ply  = 0
    base_nodes = base_time = base_ply = 0

    for result_id, stats in data.items():

        dev_nodes += stats['dev']['nodes']
        dev_time  += stats['dev']['time']
        dev_ply   += stats['dev']['ply']

        base_nodes += stats['base']['nodes']
        base_time  += stats['base']['time']
        base_ply   += stats['base']['ply']

        games += stats['dev']['games']
        assert stats['dev']['games'] == stats['base']['games']

    dev_nps  = dev_nodes  / dev_time
    base_nps = base_nodes / base_time

    dev_avg  = dev_nodes  // dev_ply
    base_avg = base_nodes // base_ply

    print ('\nStats for Dev')
    print ('-- Average KNPS  | %.3f' % (dev_nps))
    print ('-- Average Nodes | %d' % (dev_avg))

    print ('\nStats for Base')
    print ('-- Average KNPS  | %.3f' % (base_nps))
    print ('-- Average Nodes | %d' % (base_avg))

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help='Path to the OpenBench pgn archive')
    parser.add_argument('--scale' , help='Adjust based on ScaleFactor', action='store_true')
    parser.add_argument('-v', '--verbose', help='Verbose reporting per machine', action='store_true')
    args = parser.parse_args()

    data = {}
    with tarfile.open(args.filename, 'r') as tar:
        for member in filter(lambda x: x.isfile(), tar.getmembers()):
            if file := tar.extractfile(member):
                test_id, result_id, seed, _, _ = member.name.split('.')
                process_content(bz2.decompress(file.read()), data, result_id, args.scale)

    if args.verbose:
        report_verbose_stats(data)

    report_general_stats(data)


