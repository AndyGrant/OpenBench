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

# For use externally
REGEX_COMMENT_VERBOSE  = r'(book|[+-]?M?\d+(?:\.\d+)? \d+/\d+ \d+ \d+)'
REGEX_COMMENT_COMPACT  = r'(book|[+-]?M?\d+(?:\.\d+)?) \d+/\d+ \d+ \d+'
REGEX_MOVE_AND_COMMENT = r'\s*(?:\d+\. )?([a-zA-Z0-9+=#-]+) (?:\s*\{\s*([^}]*)\s*\})?'
REGEX_GAME_RESULT      = r'\s*(1-0|0-1|1/2-1/2|\*)'

def pgn_iterator(fname):
    with open(fname) as pgn:
        while True:
            headers   = pgn_header_list(iter(lambda: pgn.readline().rstrip(), ''))
            move_list = ' '.join(iter(lambda: pgn.readline().rstrip(), ''))
            if not headers or not move_list:
                break
            yield (headers, move_list)

def pgn_header_list(lines):
    # PGN Format: [<Header> "<Value>"]
    return { f.split()[0][1:] : re.search(r'"([^"]*)"', f).group(1) for f in lines }

def pgn_strip_headers(headers, compact):

    # 7-Tag Roster that is required to be a legal PGN
    desired = [
        'Event',  'Site',
        'Date',   'Round',
        'White',  'Black',
        'Result',
    ]

    desired += [
        'FEN',         # Required due to .epd openings
        'TimeControl', # Useful to extract statistics
        'Variant',     # Useful to account for FRC/DFRC
        'ScaleFactor', # Useful to extract statistics
    ]

    if not compact: # Useful to reconstruct time events
        desired += ['GameEndTime']

    # PGN Format: [<Header> "<Value>"]
    return '\n'.join('[%s "%s"]' % (f, headers[f]) for f in desired if f in headers)

def pgn_strip_movelist(move_text, compact):

    # May parse book, otherwise Score for Compact, Score Depth/SelDepth Time Nodes for Verbose
    comment_regex = re.compile(REGEX_COMMENT_COMPACT if compact else REGEX_COMMENT_VERBOSE)

    # Parses the move number, the SAN, and an optional comment
    one_ply_regex = re.compile(r'\s*(?:\d+\. )?([a-zA-Z0-9+=#-]+) (?:\s*\{\s*([^}]*)\s*\})?')

    # Captures the trailing game result
    result_regex  = re.compile(r'\s*(1-0|0-1|1/2-1/2|\*)')

    stripped = '' # Add each: <Move> {<Comment>}
    for move, comment in re.compile(REGEX_MOVE_AND_COMMENT).findall(move_text):
        match = re.search(comment_regex, comment)
        stripped += '%s {%s} ' % (move, match.group() if match else 'unknown')

    # PGNs expect trailing game result text
    return stripped + re.compile(REGEX_GAME_RESULT).search(move_text).group(1)

def strip_entire_pgn(file_name, scale_factor, compact):

    stripped = ''
    for header_dict, move_text in pgn_iterator(file_name):
        header_dict['ScaleFactor'] = str(scale_factor)
        stripped += pgn_strip_headers(header_dict, compact) + '\n\n'
        stripped += pgn_strip_movelist(move_text, compact) + '\n\n'

    return stripped

def compress_list_of_pgns(file_names, scale_factor, compact):

    text = ''
    for fname in file_names:
        print ('Compressing %s...' % (fname))
        text += strip_entire_pgn(fname, scale_factor, compact)

    return bz2.compress(text.encode())
