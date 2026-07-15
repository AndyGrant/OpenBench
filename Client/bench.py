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

# The sole purpose of this module is to invoke run_benchmark().
#
#   - binary   : Relative path to, and including, the Binary File
#   - threads  : Number of concurrent benches to run
#   - sets     : Number of times to repeat this experiment
#   - expected : None, or an expected value, which if not matched raises Exceptions
#
# run_benchmark() may raise utils.OpenBenchBadBenchException.
# An associated error message, including the binary name, is included

import multiprocessing
import os
import queue
import re
import subprocess
import threading
import time
import psutil

## Local imports must only use "import x", never "from x import ..."

import utils

MAX_BENCH_TIME_SECONDS = 60

def parse_stream_output(stream):

    nps = bench = None # Search through output Stream
    for line in stream.decode('utf-8').strip().split('\n')[::-1]:

        # Convert non alpha-numerics to spaces
        line = re.sub(r'[^a-zA-Z0-9 ]+', ' ', line)

        # Multiple methods, including Ethereal and Stockfish
        nps_pattern   = r'(\d+\s+nps)|(nps\s+\d+)|(nodes second\s+\d+)'
        bench_pattern = r'(\d+\s+nodes)|(nodes\s+\d+)|(nodes searched\s+\d+)'

        # Search for and set only once the NPS and Bench values
        re_nps = re.search(nps_pattern, line, re.IGNORECASE)
        re_bench = re.search(bench_pattern, line, re.IGNORECASE)

        # Set, but don't override
        if re_nps: nps = nps if nps else re_nps.group()
        if re_bench: bench = bench if bench else re_bench.group()

    # Parse out the integer portion from our matches
    nps   = int(re.search(r'\d+', nps  ).group()) if nps   else None
    bench = int(re.search(r'\d+', bench).group()) if bench else None
    return (bench, nps)

def single_core_bench(binary, outqueue):

    cmd = ['./%s' % (binary), 'bench']

    try: # Launch the bench and wait for results
        stdout, stderr = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ).communicate()
        outqueue.put(parse_stream_output(stdout))

    except: # Signal an error with (None, None)
        outqueue.put((None, None))

def multi_core_bench(binary, threads, monitor_memory=False):

    outqueue = multiprocessing.Queue()

    processes = [
        multiprocessing.Process(
            target=single_core_bench, args=(binary, outqueue))
        for ii in range(threads)
    ]

    for process in processes:
        process.start()

    stop_event     = None
    monitor        = None
    monitor_result = {}

    if monitor_memory:
        pids           = [process.pid for process in processes]
        stop_event     = threading.Event()
        monitor        = threading.Thread(target=monitor_peak_memory, args=(pids, stop_event, monitor_result))
        monitor.start()

    try: # Every process deposits exactly one result into the Queue
        results = [outqueue.get(timeout=MAX_BENCH_TIME_SECONDS) for _ in range(threads)]

    except queue.Empty: # Force kill the engine, thus causing the processes to finish
        utils.kill_process_by_name(binary)
        raise utils.OpenBenchBadBenchException('[%s] Bench Exceeded Max Duration' % (binary))

    finally: # Join everything to avoid zombie processes
        if monitor_memory:
            stop_event.set()
            monitor.join()
        for process in processes:
            process.join()

    return results, monitor_result.get('peak', 0)

def run_benchmark(binary, threads, sets, expected=None, monitor_memory=False):

    engine = os.path.basename(binary)

    peak_memory = 0
    benches, speeds = [], []
    for _ in range(sets):
        results, peak_memory_run = multi_core_bench(binary, threads, monitor_memory)

        for bench, speed in results:
            benches.append(bench); speeds.append(speed)

        if monitor_memory:
            peak_memory = max(peak_memory, peak_memory_run)

    if None in benches or None in speeds:
        raise utils.OpenBenchBadBenchException('[%s] Failed to Execute Benchmark' % (engine))

    if len(set(benches)) != 1:
        raise utils.OpenBenchBadBenchException('[%s] Non-Deterministic Benches' % (engine))

    if expected and expected != benches[0]:
        raise utils.OpenBenchBadBenchException('[%s] Wrong Bench: %d' % (engine, benches[0]))

    return sum(speeds) // len(speeds), benches[0], peak_memory

def sample_engine_memory(workers):

    total = 0
    for worker in workers:
        try: # Engines are direct children of the multiprocessing workers
            for engine in worker.children(recursive=True):
                try:
                    info = engine.memory_full_info()
                    total += getattr(info, 'pss', info.uss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return total

def monitor_peak_memory(worker_pids, stop_event, result):

    MEMORY_SAMPLE_SECONDS = 0.1

    workers = []
    for pid in worker_pids:
        try: workers.append(psutil.Process(pid))
        except psutil.NoSuchProcess: pass

    peak = 0
    while not stop_event.is_set():
        peak = max(peak, sample_engine_memory(workers))
        time.sleep(MEMORY_SAMPLE_SECONDS)

    result['peak'] = max(peak, sample_engine_memory(workers))
