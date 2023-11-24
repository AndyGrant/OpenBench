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

import bz2
import re
import sys

def pgn_iterator(fname):
    with open(fname) as pgn:
        while True:
            headers   = pgn_list_to_headers(iter(lambda: pgn.readline().rstrip(), ''))
            move_list = ' '.join(iter(lambda: pgn.readline().rstrip(), ''))
            if not headers or not move_list:
                break
            yield (headers, move_list)

def pgn_list_to_headers(lines):
    # PGN Format: [<Header> "<Value>"]
    return { f.split()[0][1:] : re.search(r'"([^"]*)"', f).group(1) for f in lines }

def pgn_strip_headers(headers):
    # PGN Format: [<Header> "<Value>"]
    desired = [ 'White', 'Black', 'Result', 'PlyCount', 'FEN', 'TimeControl' ]
    return '\n'.join('[%s "%s"]' % (f, headers[f]) for f in desired)

def pgn_strip_movelist(move_text, compact):

    if not compact: # Captures Score Depth/SelDepth Time Nodes
        comment_regex = r'([+-]?M?\d+(?:\.\d+)? \d+/\d+ \d+ \d+)[^}]*'

    else: # Captures Score and nothing else
        comment_regex = r'([+-]?M?\d+(?:\.\d+)?) \d+/\d+ \d+ \d+[^}]*'

    # Captures the Move and Comment, discarding extra commentary and move numbers
    one_ply_regex = re.compile(r'\s*(?:\d+\. )?([a-zA-Z0-9+=#-]+) {%s}' % (comment_regex))

    # Captures the trailing game result
    result_regex  = re.compile(r'\s*(1-0|0-1|1/2-1/2|\*)')

    stripped = '' # Add each: <Move> {<Comment>}
    for move, comment in one_ply_regex.findall(move_text):
        stripped += '%s {%s} ' % (move, comment)

    # PGNs expect trailing game result text
    return stripped + result_regex.search(move_text).group(1)

def strip_entire_pgn(file_name, compact=True):

    stripped = ''
    for header_dict, move_text in pgn_iterator(sys.argv[1]):
        stripped += pgn_strip_headers(header_dict) + '\n'
        stripped += pgn_strip_movelist(move_text, compact) + '\n'

    return stripped


if __name__ == '__main__':

    text = strip_entire_pgn(sys.argv[1], compact=True)

    compressed = bz2.compress(text.encode())
