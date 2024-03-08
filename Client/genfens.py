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

import math
import multiprocessing
import os
import subprocess
import time

def create_genfens_opening_book(config, binary_name, network):

    # Format: ./engine "genfens N seed S book <None|book.epd>" "quit"
    binary      = os.path.join('Engines', binary_name)
    extra_args  = config.workload['test']['genfens_args']
    repeat      = config.workload['test']['play_reverses']
    private     = config.workload['test']['dev']['private']
    seed        = config.workload['test']['book_index']

    # Provide the book or "None"
    book_name   = config.workload['test']['book']['name']
    book_none   = book_name.upper() == 'NONE'
    book_str    = 'None' if book_none else os.path.join('Books', book_name)

    # Number of opening lines needed from each worker Thread
    cutechess_cnt = config.workload['distribution']['cutechess-count']
    games_per     = config.workload['distribution']['games-per-cutechess']
    total_games   = cutechess_cnt * games_per // 2 if repeat else cutechess_cnt * games_per
    N             = math.ceil(total_games / config.threads)

    print ('\nGenerating %d Openings using %d Threads...' % (N * config.threads, config.threads))
    start_time = time.time()

    # Execute all the helpers, who will dump results into the Queue
    queue = multiprocessing.Queue()
    for f in range(config.threads):
        command = genfens_command_builder(binary, network, private, N, seed, book_str, extra_args)
        multiprocessing.Process(target=genfens_single_threaded, args=(command, queue)).start()
        seed += N # Step the seed ahead to vary it over the Threads

    # Parse the Queue and save the content into Books/openbench.genfens.epd
    with open(os.path.join('Books', 'openbench.genfens.epd'), 'w') as fout:
        for iteration in range(N * config.threads):
            fout.write(queue.get() + '\n')
            genfens_progress_bar(iteration+1, N * config.threads)

    print('\nFinished Building Opening Book in %.3f seconds' % (time.time() - start_time))

def genfens_command_builder(binary, network, private, N, seed, book_str, extra_args):

    command = ['./%s' % (binary)]

    if network and private:
        command += ['setoption name EvalFile value %s' % (network)]

    command += ['genfens %d seed %d book %s %s' % (N, seed, book_str, extra_args), 'quit']

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
