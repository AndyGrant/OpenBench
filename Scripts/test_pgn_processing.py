#!/usr/bin/env python3

import argparse
import io
import os
import sys

import chess.pgn

# Needed to include from ../Client/*.py
PARENT = os.path.join(os.path.dirname(__file__), os.path.pardir)
sys.path.append(os.path.abspath(os.path.join(PARENT, 'Client')))

from pgn_util import process_pgn_file

def parse_pgn_string(pgn_text):
    games = []
    pgn_io = io.StringIO(pgn_text)
    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None:
            break
        games.append(game)
    return games

def get_moves(game):
    moves = []
    node = game
    while node.variations:
        node = node.variations[0]
        moves.append(node.move)
    return moves

def validate(original_games, processed_games):

    errors = []

    if len(original_games) != len(processed_games):
        errors.append('Game count mismatch: original=%d, processed=%d' % (len(original_games), len(processed_games)))
        return errors

    for i, (orig, proc) in enumerate(zip(original_games, processed_games)):

        tag = 'Game %d' % (i + 1)

        orig_fen = orig.headers.get('FEN', '')
        proc_fen = proc.headers.get('FEN', '')
        if orig_fen != proc_fen:
            errors.append('%s: FEN mismatch\n  original : %s\n  processed: %s' % (tag, orig_fen, proc_fen))

        orig_result = orig.headers.get('Result', '*')
        proc_result = proc.headers.get('Result', '*')
        if orig_result != proc_result:
            errors.append('%s: Result mismatch: original=%r processed=%r' % (tag, orig_result, proc_result))

        orig_moves = get_moves(orig)
        proc_moves = get_moves(proc)

        if len(orig_moves) != len(proc_moves):
            errors.append('%s: Move count mismatch: original=%d processed=%d' % (tag, len(orig_moves), len(proc_moves)))
            errors.append('  original : %s' % ' '.join(m.uci() for m in orig_moves))
            errors.append('  processed: %s' % ' '.join(m.uci() for m in proc_moves))
            continue

        for j, (om, pm) in enumerate(zip(orig_moves, proc_moves)):
            if om != pm:
                errors.append('%s: Move %d mismatch: original=%s processed=%s' % (tag, j + 1, om.uci(), pm.uci()))

    return errors

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Validate PGN processing against original')
    parser.add_argument('--pgn', required=True, help='Path to PGN file')

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--compact', action='store_true')
    mode_group.add_argument('--verbose', action='store_true')

    args = parser.parse_args()

    with open(args.pgn) as f:
        original_text = f.read()

    original_games  = parse_pgn_string(original_text)
    processed_text  = process_pgn_file(args.pgn, scale_factor=1.0, compact=args.compact)
    processed_games = parse_pgn_string(processed_text)

    print('Parsed %d original / %d processed games from %s' % (len(original_games), len(processed_games), args.pgn))

    errors = validate(original_games, processed_games)

    if errors:
        print('FAIL: %d error(s) found:' % len(errors))
        for e in errors:
            print(' ', e)
        sys.exit(1)

    print('PASS: all %d games validated' % len(original_games))
