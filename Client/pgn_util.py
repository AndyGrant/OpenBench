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
import bz2
import re

## Local imports must only use "import x", never "from x import ..."

def read_until_empty_line(pgn):

    lines = []
    while True:
        line = pgn.readline().rstrip()
        if not line:
            break
        lines.append(line)
    return lines

def pgn_iterator(fname):

    with open(fname) as pgn:
        while True:

            header_lines = read_until_empty_line(pgn)
            move_lines   = read_until_empty_line(pgn)
            if not header_lines or not move_lines:
                break

            headers   = { line.split()[0][1:] : re.search(r'"([^"]*)"', line).group(1) for line in header_lines }
            move_text = ' '.join(move_lines)

            yield (headers, move_text)

def tag_players(headers, players):

    # The match runner plays <engine>-dev and <engine>-base; the fork names them as its match document
    # does, <engine> <branch>, and tags dev's colour and the opponent (nyayo's game database)
    renamed = dict(headers)
    for colour in ('White', 'Black'):
        name = headers.get(colour, '')
        side = 'dev' if name.endswith('-dev') else 'base' if name.endswith('-base') else None
        if side:
            renamed[colour] = players[side].replace('"', "'")
        if side == 'dev':
            renamed['Subject'] = colour.lower()
    renamed['Opponent'] = 'base'
    return renamed

def format_headers(headers, compact, players=None):

    # players: { 'dev' : <name>, 'base' : <name> }, the final names of the match runner's <engine>-<side>
    if players:
        headers = tag_players(headers, players)

    desired  = ['Event', 'Site', 'Date', 'Round', 'White', 'Black', 'Result']
    desired += ['FEN', 'TimeControl', 'Variant', 'ScaleFactor', 'SetUp']
    desired += ['Termination'] # Tells an adjudication from a time loss or a crash

    if not compact:
        desired += ['GameEndTime']

    desired += ['Subject', 'Opponent'] # The fork's, from tag_players()

    return '\n'.join('[%s "%s"]' % (key, headers[key]) for key in desired if key in headers)

def format_move_comment(comment):

    # The match runner's whole comment per move (score/depth, time, nodes, seldepth, ...), whitespace tidied
    return re.sub(r'\s+', ' ', comment).strip()

def format_movelist(move_text, compact):

    moves = []

    for move, comment in re.compile(r'\s*(?:\d+\.{1,3} )?([a-zA-Z0-9+=#*-]+) (?:\s*\{\s*([^}]*)\s*\})?').findall(move_text):
        if not comment or comment.strip() == 'book':
            formatted_comment = comment.strip() if comment else 'unknown'
        else:
            formatted_comment = format_move_comment(comment)

        moves.append('%s {%s}' % (move, formatted_comment))

    result_match = re.search(r'\s*(1-0|0-1|1/2-1/2|\*)', move_text)
    result       = result_match.group(1) if result_match else '*'

    return ' '.join(moves) + ' ' + result

def process_pgn_file(file_name, scale_factor, compact, players=None):

    output = []

    for headers, move_text in pgn_iterator(file_name):
        headers['ScaleFactor'] = str(scale_factor)
        output.append(format_headers(headers, compact, players))
        output.append('')
        output.append(format_movelist(move_text, compact))
        output.append('')

    return '\n'.join(output)

def compress_pgn_files(file_names, scale_factor, compact, players=None):

    compressed_text = []
    for fname in file_names:
        print ('Compressing %s...' % fname)
        compressed_text.append(process_pgn_file(fname, scale_factor, compact, players))

    return bz2.compress('\n'.join(compressed_text).encode())

def collect_nps_stats(pgn_files, scale_factor):

    nps_regex = re.compile(r'([\d.]+)s,\s*n=(\d+)')

    stats = {
        'dev' : { 'nodes': 0, 'time': 0, 'time_scaled': 0 },
        'base': { 'nodes': 0, 'time': 0, 'time_scaled': 0 },
    }

    for file in pgn_files:
        for (headers, move_text) in pgn_iterator(file):

            white     = headers['White'].split('-')[-1]
            black     = headers['Black'].split('-')[-1]
            white_stm = 'FEN' not in headers or headers['FEN'].split()[1] == 'w'

            for time, nodes in nps_regex.findall(move_text):
                stm = white if white_stm else black
                if stm in stats:
                    stats[stm]['nodes']       += int(nodes)
                    stats[stm]['time']        += float(time) * 1000
                    stats[stm]['time_scaled'] += float(time) * 1000 / scale_factor
                white_stm = not white_stm

    return stats

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Process PGN files')
    parser.add_argument('--pgn', required=True, help='Path to PGN file')

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--compact', action='store_true', help='Use compact mode')
    mode_group.add_argument('--verbose', action='store_true', help='Use verbose mode')

    args = parser.parse_args()

    result = process_pgn_file(args.pgn, scale_factor=1.0, compact=args.compact)
    print (result)
