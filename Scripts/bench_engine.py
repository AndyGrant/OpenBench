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

def single_core_bench(engine, outqueue):

    # Launch the bench and wait for results
    stdout, stderr = subprocess.Popen(
        './{0} bench'.format(engine).split(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()

    outqueue.put(parse_stream_output(stdout))

def multi_core_bench(engine, threads):

    outqueue = multiprocessing.Queue()

    processes = [
        multiprocessing.Process(
            target=single_core_bench,
            args=(engine, outqueue)
        ) for ii in range(threads)
    ]

    for process in processes: process.start()

    return [outqueue.get() for ii in range(threads)]

def run_benchmark(engine, threads, sets):

    benches, speeds = [], []
    for ii in range(sets):
        for bench, speed in multi_core_bench(engine, threads):
            benches.append(bench); speeds.append(speed)

    if len(set(benches)) != 1:
        print("Error: Non-Deterministic Results!")
        sys.exit()

    return int(sum(speeds) / len(speeds))

if __name__ == '__main__':

    p = argparse.ArgumentParser()
    p.add_argument('-E', '--engine'  , help='Binary Name',            required=True)
    p.add_argument('-T', '--threads' , help='Concurrent Benchmarks',  required=True)
    p.add_argument('-S', '--sets'    , help='Benchmark Sample Count', required=True)
    args = p.parse_args()

    print (run_benchmark(args.engine, int(args.threads), int(args.sets)))
