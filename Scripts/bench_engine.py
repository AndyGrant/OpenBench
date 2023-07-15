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
import multiprocessing
import re
import subprocess
import sys

def parse_stream_output(stream):

    nps = bench = None # Search through output Stream
    for line in stream.decode('ascii').strip().split('\n')[::-1]:

        # Convert non alpha-numerics to spaces
        line = re.sub(r'[^a-zA-Z0-9 ]+', ' ', line)

        # Multiple methods, including Ethereal and Stockfish
        nps_pattern   = r'(\d+\s+nps)|(nps\s+\d+)|(nodes second\s+\d+)'
        bench_pattern = r'(\d+\s+nodes)|(nodes\s+\d+)|(nodes searched\s+\d+)'

        # Search for and set only once the NPS value
        if (re_nps := re.search(nps_pattern, line, re.IGNORECASE)):
            nps = nps if nps else re_nps.group()

        # Search for and set only once the Bench value
        if (re_bench := re.search(bench_pattern, line, re.IGNORECASE)):
            bench = bench if bench else re_bench.group()

    # Parse out the integer portion from our matches
    nps   = int(re.search(r'\d+', nps  ).group()) if nps   else None
    bench = int(re.search(r'\d+', bench).group()) if bench else None
    return (bench, nps)

def single_core_bench(engine, network, outqueue):

    # Basic command for Public engines
    cmd = ['./' + engine, 'bench']

    # Adjust to handle setting Networks in Private engines
    if network:
        option = 'setoption name EvalFile value %s' % (network)
        cmd = ['./%s' % (engine), option, 'bench', 'quit']

    # Launch the bench and wait for results
    stdout, stderr = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).communicate()

    outqueue.put(parse_stream_output(stdout))

def multi_core_bench(engine, network, threads):

    outqueue = multiprocessing.Queue()

    processes = [
        multiprocessing.Process(
            target=single_core_bench,
            args=(engine, network, outqueue)
        ) for ii in range(threads)
    ]

    for process in processes: process.start()
    return [outqueue.get() for ii in range(threads)]

def run_benchmark(engine, network, threads, sets):

    benches, speeds = [], []
    for ii in range(sets):
        for bench, speed in multi_core_bench(engine, network, threads):
            benches.append(bench); speeds.append(speed)

    if len(set(benches)) != 1:
        print("Error: Non-Deterministic Results!")
        return (0, 0)

    return int(sum(speeds) / len(speeds)), benches[0]

if __name__ == '__main__':

    p = argparse.ArgumentParser()
    p.add_argument('-E', '--engine'  , help='Binary Name',                  required=True)
    p.add_argument('-N', '--network' , help='Networks for Private Engines', required=False)
    p.add_argument('-T', '--threads' , help='Concurrent Benchmarks',        required=True)
    p.add_argument('-S', '--sets'    , help='Benchmark Sample Count',       required=True)
    args = p.parse_args()

    print (run_benchmark(args.engine, args.network, int(args.threads), int(args.sets)))
