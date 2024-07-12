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

# The sole purpose of this module is to invoke create_genfens_opening_book().
#
# This will execute engines with commands like the following:
#   ./engine "genfens N seed S book <None|Books/book.epd> <?extra>" "quit"
#
# This work is split over many engines. If a workload requires 1024 openings,
# and there are 16 threads, then each thread will generate 64 openings. The
# openings are saved to Books/openbench.genfens.epd
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

from utils import kill_process_by_name
from utils import OpenBenchFailedGenfensException

def genfens_required_openings_each(config):

    cutechess_cnt = config.workload['distribution']['cutechess-count']
    games_per     = config.workload['distribution']['games-per-cutechess']
    repeat        = config.workload['test']['play_reverses']
    total_games   = cutechess_cnt * games_per // (1 + repeat)

    return math.ceil(total_games / config.threads)

def genfens_command_args(config, binary_name, network):

    binary      = os.path.join('Engines', binary_name)
    private     = config.workload['test']['dev']['private']
    N           = genfens_required_openings_each(config)
    book        = genfens_book_input_name(config)
    extra_args  = config.workload['test']['genfens_args']

    return (binary, network, private, N, book, extra_args)

def genfens_book_input_name(config):

    book_name   = config.workload['test']['book']['name']
    book_none   = book_name.upper() == 'NONE'

    return 'None' if book_none else os.path.join('Books', book_name)

def genfens_command_builder(binary, network, private, N, book, extra_args, seed):

    command = ['./%s' % (binary)]

    if network and private:
        command += ['setoption name EvalFile value %s' % (network)]

    command += ['genfens %d seed %d book %s %s' % (N, seed, book, extra_args), 'quit']

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

    prev_progress = int(50 * (curr - 1) / total)
    curr_progress = int(50 * (curr - 0) / total)

    if curr_progress != prev_progress:
        bar_text = '=' * curr_progress + ' ' * (50 - curr_progress)
        print ('\r[%s] %d/%d' % (bar_text, curr, total), end='', flush=True)

def create_genfens_opening_book(config, binary_name, network):

    # Format: ./engine "genfens N seed S book <None|book.epd>" "quit"
    N     = genfens_required_openings_each(config)
    seed  = config.workload['test']['book_index']
    args  = genfens_command_args(config, binary_name, network)

    start_time = time.time()
    output     = multiprocessing.Queue()
    print ('\nGenerating %d Openings using %d Threads...' % (N * config.threads, config.threads))

    # Split the work over many threads. Ensure the seed varies by the thread,
    # number in accordance with how many openings each thread will generate
    processes = [
        multiprocessing.Process(
            target=genfens_single_threaded,
            args=(genfens_command_builder(*args, seed + ii * N), output))
        for ii in range(config.threads)
    ]

    for process in processes:
        process.start()

    # Parse the Queue and save the content into Books/openbench.genfens.epd
    with open(os.path.join('Books', 'openbench.genfens.epd'), 'w') as fout:

        try: # Each process will deposit exactly N results into the Queue
            for iteration in range(N * config.threads):
                fout.write(output.get(timeout=15) + '\n')
                genfens_progress_bar(iteration+1, N * config.threads)

        except queue.Empty: # Force kill the engine, thus causing the processes to finish
            kill_process_by_name(binary_name)
            raise OpenBenchFailedGenfensException('[%s] Stalled during genfens' % (binary_name))

        finally: # Join everything to avoid zombie processes
            for process in processes:
                process.join()

    print('\nFinished Building Opening Book in %.3f seconds' % (time.time() - start_time))
