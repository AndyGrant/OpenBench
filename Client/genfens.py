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

# The main purpose of this module is to invoke create_genfens_opening_book().
# Refer to Client/worker.py, or Scripts/genfens_engine.py for the arguments.
#
# We will execute engines with commands like the following:
#   ./engine "genfens N seed S book <None|Books/book.epd> <?extra>" "quit"
#
# This work is split over many engines. If a workload requires 1024 openings,
# and there are 16 threads, then each thread will generate 64 openings.
#
# create_genfens_opening_book() may raise utils.OpenBenchFailedGenfensException.
# This occurs when longer than 15 seconds has elapsed since getting an opening.
# This should only occur if one or more of the engine processes has stalled.

import math
import os
import queue
import subprocess
import time
import multiprocessing

## Local imports must only use "import x", never "from x import ..."

import utils

def genfens_required_openings_each(config):

    runner_cnt  = config.workload['distribution']['runner-count']
    games_per   = config.workload['distribution']['games-per-runner']
    repeat      = config.workload['test']['play_reverses']
    total_games = runner_cnt * games_per // (1 + repeat)

    return math.ceil(total_games / config.threads)

def genfens_book_input_name(config):

    book_name = config.workload['test']['book']['name']
    book_none = book_name.upper() == 'NONE'

    return 'None' if book_none else os.path.join('Books', book_name)

def genfens_command_builder(args, index):

    command = ['./%s' % (args['engine'])]

    if args['network'] and args['private']:
        command += ['setoption name EvalFile value %s' % (args['network'])]

    fstr = 'genfens %d seed %d book %s %s'
    command += [fstr % (args['N'], args['seeds'][index], args['book'], args['extra']), 'quit']

    return command

def genfens_single_threaded(command, queue):

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        for line in iter(process.stdout.readline, b''):
            if line.decode('utf-8').startswith('info string genfens '):
                queue.put(line.decode('utf-8').split('genfens ')[1].rstrip())

        process.wait()

    except:
        raise

def genfens_progress_bar(curr, total):

    prev_progress = 50 * (curr - 1) // total
    curr_progress = 50 * (curr - 0) // total

    if curr_progress != prev_progress:
        bar_text = '=' * curr_progress + ' ' * (50 - curr_progress)
        print ('\r[%s] %d/%d' % (bar_text, curr, total), end='', flush=True)

def convert_fen_to_epd(fen):

    # Input  : rnbqkbnr/pppp2pp/4pp2/8/2P2P2/P7/1P1PP1PP/RNBQKBNR b KQkq - 0 3
    # Output : rnbqkbnr/pppp2pp/4pp2/8/2P2P2/P7/1P1PP1PP/RNBQKBNR b KQkq - hmvc 0; fmvn 3;

    halfmove, fullmove = fen.split()[4:]

    return ' '.join(fen.split()[:4]) + ' hmvc %d; fmvn %d;' % (int(halfmove), int(fullmove))

def create_genfens_opening_book(args):

    N          = args['N']
    threads    = args['threads']
    start_time = time.time()
    output     = multiprocessing.Queue()

    print ('\nGenerating %d Openings using %d Threads...' % (N * threads, threads))

    # Split the work over many threads. Ensure the seed varies by the thread,
    # number in accordance with how many openings each thread will generate

    processes = [
        multiprocessing.Process(
            target=genfens_single_threaded,
            args=(genfens_command_builder(args, index), output))
        for index in range(threads)
    ]

    for process in processes:
        process.start()

    try: # Each process will deposit exactly N results into the Queue
        for iteration in range(N * threads):
            args['output'].write(convert_fen_to_epd(output.get(timeout=15)) + '\n')
            genfens_progress_bar(iteration+1, N * threads)

    except queue.Empty: # Force kill the engine, thus causing the processes to finish
        utils.kill_process_by_name(args['engine'])
        raise utils.OpenBenchFailedGenfensException('[%s] Stalled during genfens' % (args['engine']))

    finally: # Join everything to avoid zombie processes
        for process in processes:
            process.join()

    print('\nFinished Building Opening Book in %.3f seconds' % (time.time() - start_time))
