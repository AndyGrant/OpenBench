import argparse
import multiprocessing
import re
import subprocess
import sys

def parse_stream_output(stream):

    nps = bench = None # Search through output Stream
    for line in stream.decode('ascii').strip().split('\n')[::-1]:

        # Try to match a wide array of patterns
        line = re.sub(r'[^a-zA-Z0-9 ]+', ' ', line)
        nps_pattern = r'([0-9]+ NPS)|(NPS[ ]+[0-9]+)'
        bench_pattern = r'([0-9]+ NODES)|(NODES[ ]+[0-9]+)'
        re_nps = re.search(nps_pattern, line.upper())
        re_bench = re.search(bench_pattern, line.upper())

        # Replace only if not already found earlier
        if not nps and re_nps: nps = re_nps.group()
        if not bench and re_bench: bench = re_bench.group()

    # Parse out the integer portion from our matches
    nps = int(re.search(r'[0-9]+', nps).group()) if nps else None
    bench = int(re.search(r'[0-9]+', bench).group()) if bench else None
    return (bench, nps)

def single_core_bench(engine, outqueue):

    # Launch the bench and wait for results
    stdout, stderr = subprocess.Popen(
        "./{0} bench".format(engine).split(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()

    # Parse output streams for the benchmark data
    bench, speed = parse_stream_output(stdout)
    if bench is None or speed is None:
        bench, speed = parse_stream_output(stderr)
    outqueue.put((int(bench), int(speed)))

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
