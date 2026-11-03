# A toy UCI engine for the OpenBench smoke test. It plays a random legal move,
# seeded by the position, so a game is reproducible. `bench` always prints BENCH;
# a bench mismatch is a test whose expected bench differs. Two options misbehave
# on purpose: Strength 0 plays any legal move (1, the default, prefers mates and
# captures), and CrashAfter N exits without a word after N moves (0: never).
#
# The makefile turns this file into the executable the worker builds.

import hashlib
import os
import random
import sys
import time

import chess

BENCH = 1000000
NPS   = 1000000

# How the bench misbehaves, set where the zip is made (files.engine_zip): slow (outlasts the worker's wait), silent
# (prints no count: failed to execute), flip (right the first time, wrong from the second on)
BENCH_MODE = ''

def bench():
    nodes = BENCH
    if BENCH_MODE == 'slow':
        time.sleep(30)
    elif BENCH_MODE == 'silent':
        return
    elif BENCH_MODE == 'flip':
        counter = os.path.abspath(sys.argv[0]) + '.benches'
        with open(counter, 'a') as fout:
            fout.write('x')
        if os.path.getsize(counter) > 1:
            nodes += 1
    print('%d nodes %d nps' % (nodes, NPS), flush=True)

PIECE_VALUES = { chess.PAWN : 100, chess.KNIGHT : 300, chess.BISHOP : 300, chess.ROOK : 500, chess.QUEEN : 900 }

def material(board, color):
    # Material balance for color; reported as the score so cutechess adjudicates
    return sum(value * (len(board.pieces(piece, color)) - len(board.pieces(piece, not color)))
               for piece, value in PIECE_VALUES.items())

def choose_move(board, seed, strength):
    moves = sorted(board.legal_moves, key=lambda move: move.uci())
    digest = hashlib.sha256(('%s %d' % (board.fen(), seed)).encode()).digest()
    rng    = random.Random(digest)
    if not strength:
        return rng.choice(moves)
    # Mates and captures first, so random games end before the 50-move rule
    for move in moves:
        board.push(move)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return move
    captures = [move for move in moves if board.is_capture(move)]
    return rng.choice(captures if captures and rng.random() < 0.7 else moves)

def parse_position(tokens):
    board = chess.Board()
    if tokens[1:2] == ['fen']:
        end   = tokens.index('moves') if 'moves' in tokens else len(tokens)
        board = chess.Board(' '.join(tokens[2:end]))
    if 'moves' in tokens:
        for uci in tokens[tokens.index('moves') + 1:]:
            board.push_uci(uci)
    return board

def uci_loop():
    board, played = chess.Board(), 0
    options       = { 'CrashAfter' : 0, 'Seed' : 0, 'Strength' : 1 }

    for line in sys.stdin:
        tokens = line.split()
        if not tokens:
            continue

        if tokens[0] == 'uci':
            print('id name smoke')
            print('id author OpenBench smoke test')
            print('option name Threads type spin default 1 min 1 max 1')
            print('option name Hash type spin default 1 min 1 max 1024')
            print('option name CrashAfter type spin default 0 min 0 max 100000')
            print('option name Seed type spin default 0 min 0 max 100000')
            print('option name Strength type spin default 1 min 0 max 1')
            print('uciok', flush=True)

        elif tokens[0] == 'isready':
            print('readyok', flush=True)

        elif tokens[0] == 'setoption' and 'name' in tokens and 'value' in tokens:
            name  = ' '.join(tokens[tokens.index('name') + 1:tokens.index('value')])
            value = ' '.join(tokens[tokens.index('value') + 1:])
            if name in options:
                options[name] = int(value)

        elif tokens[0] == 'ucinewgame':
            board = chess.Board()

        elif tokens[0] == 'position':
            board = parse_position(tokens)

        elif tokens[0] == 'go':
            if options['CrashAfter'] and played >= options['CrashAfter']:
                os._exit(1)
            move    = choose_move(board, options['Seed'], options['Strength'])
            played += 1
            mover   = board.turn
            board.push(move)
            print('info depth 1 nodes 1 score cp %d pv %s' % (material(board, mover), move.uci()))
            print('bestmove %s' % (move.uci()), flush=True)

        elif tokens[0] == 'bench':
            bench()

        elif tokens[0] == 'quit':
            break

if __name__ == '__main__':
    if sys.argv[1:2] == ['bench']:
        bench()
    else:
        uci_loop()
