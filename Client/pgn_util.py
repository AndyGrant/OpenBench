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

def format_headers(headers, compact):

    desired  = ['Event', 'Site', 'Date', 'Round', 'White', 'Black', 'Result']
    desired += ['FEN', 'TimeControl', 'Variant', 'ScaleFactor', 'SetUp']

    if not compact:
        desired += ['GameEndTime']

    return '\n'.join('[%s "%s"]' % (key, headers[key]) for key in desired if key in headers)

def extract_pgncomment(comment):

    match = re.search(r'line="([^"]*)"', comment)
    if not match:
        return None

    line_content = match.group(1)
    prefix       = "info string pgncomment "

    if line_content.startswith(prefix):
        return line_content[len(prefix):]

    return None

def format_move_comment_compact(comment):

    pgncomment  = extract_pgncomment(comment)
    score_depth = re.search(r'([+-]?M?\d+(?:\.\d+)?)/(\d+)', comment)

    if score_depth and pgncomment:
        return '%s, line=%s' % (score_depth.group(0), pgncomment)
    if score_depth:
        return score_depth.group(0)
    return 'unknown'

def format_move_comment_verbose(comment):

    pgncomment  = extract_pgncomment(comment)
    score_depth = re.search(r'([+-]?M?\d+(?:\.\d+)?)/(\d+)', comment)
    time        = re.search(r'([\d.]+s)', comment)
    nodes       = re.search(r'n=(\d+)', comment)
    seldepth    = re.search(r'sd=(\d+)', comment)

    if not (score_depth and time and nodes and seldepth):
        return 'unknown'

    parts = [
        '%s %s' % (score_depth.group(0), time.group(1)),
        'n=%s' % nodes.group(1),
        'sd=%s' % seldepth.group(1),
    ]

    if pgncomment:
        parts.append('line=%s' % pgncomment)

    return ', '.join(parts)

def format_movelist(move_text, compact):

    formatter = format_move_comment_compact if compact else format_move_comment_verbose
    moves     = []

    for move, comment in re.compile(r'\s*(?:\d+\.{1,3} )?([a-zA-Z0-9+=#*-]+) (?:\s*\{\s*([^}]*)\s*\})?').findall(move_text):
        if not comment or comment.strip() == 'book':
            formatted_comment = comment.strip() if comment else 'unknown'
        else:
            formatted_comment = formatter(comment)

        moves.append('%s {%s}' % (move, formatted_comment))

    result_match = re.search(r'\s*(1-0|0-1|1/2-1/2|\*)', move_text)
    result       = result_match.group(1) if result_match else '*'

    return ' '.join(moves) + ' ' + result

def process_pgn_file(file_name, scale_factor, compact):

    output = []

    for headers, move_text in pgn_iterator(file_name):
        headers['ScaleFactor'] = str(scale_factor)
        output.append(format_headers(headers, compact))
        output.append('')
        output.append(format_movelist(move_text, compact))
        output.append('')

    return '\n'.join(output)

def compress_pgn_files(file_names, scale_factor, compact):

    text = ''
    for fname in file_names:
        print ('Compressing %s...' % fname)
        text += process_pgn_file(fname, scale_factor, compact)

    return bz2.compress(text.encode())

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Process PGN files')
    parser.add_argument('--pgn', required=True, help='Path to PGN file')

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--compact', action='store_true', help='Use compact mode')
    mode_group.add_argument('--verbose', action='store_true', help='Use verbose mode')

    args = parser.parse_args()

    result = process_pgn_file(args.pgn, scale_factor=1.0, compact=args.compact)
    print (result)
