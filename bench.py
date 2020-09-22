import re, multiprocessing, os, subprocess, sys, time

def parseStreamOutput(output):

    # None unless found
    bench = None; speed = None

    # Split the output line by line and look backwards
    for line in output.decode('ascii').strip().split('\n')[::-1]:

        # Convert all non-alpha numerics to spaces
        line = re.sub(r'[^a-zA-Z0-9 ]+', ' ', line)

        # Search for node or speed counters
        bench1 = re.search(r'[0-9]+ NODES', line.upper())
        bench2 = re.search(r'NODES[ ]+[0-9]+', line.upper())
        speed1 = re.search(r'[0-9]+ NPS'  , line.upper())
        speed2 = re.search(r'NPS[ ]+[0-9]+'  , line.upper())

        # A line with no parsable information was found
        if not bench1 and not bench2 and not speed1 and not speed2:
            break

        # A Bench value was found
        if not bench and (bench1 or bench2):
            bench = bench1.group() if bench1 else bench2.group()

        # A Speed value was found
        if not speed and (speed1 or speed2):
            speed = speed1.group() if speed1 else speed2.group()

    # Parse out the integer portion from our matches
    bench = int(re.search(r'[0-9]+', bench).group()) if bench else None
    speed = int(re.search(r'[0-9]+', speed).group()) if speed else None
    return (bench, speed)

def singleCoreBench(engine, outqueue):

    # Launch the bench and wait for results
    stdout, stderr = subprocess.Popen(
        "./{0} bench".format(engine).split(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()

    # Parse output streams for the benchmark data
    bench, speed = parseStreamOutput(stdout)
    if bench is None or speed is None:
        bench, speed = parseStreamOutput(stderr)
    outqueue.put((int(bench), int(speed)))

def multiCoreBench(engine, threads):

    # Give time for any previous run to finish
    time.sleep(2)

    # Dump results into a Queue
    outqueue = multiprocessing.Queue()

    # Spawn each singleCoreBench()
    processes = [
        multiprocessing.Process(
            target=singleCoreBench,
            args=(engine, outqueue)
        ) for ii in range(threads)
    ]

    # Launch each singleCoreBench()
    for process in processes:
        process.start()

    # Wait for each thread and collect data
    return [outqueue.get() for ii in range(threads)]

if __name__ == "__main__":

    # Check for arguments
    if len(sys.argv) < 4:
        print("Usage: python3 bench.py <Engine> <Threads> <Sets>")
        sys.exit()

    # Run each parrallel test
    benches = []; speeds = []
    for ii in range(int(sys.argv[3])):
        for bench, speed in multiCoreBench(sys.argv[1], int(sys.argv[2])):
            benches.append(bench); speeds.append(speed)

    # Log per-thread and per-set data
    for ii in range(int(sys.argv[3])):
        print("\nBenchmark Run #{0:>2}".format(ii))
        for jj in range(int(sys.argv[2])):
            index = ii * int(sys.argv[3]) + jj
            print("Thread #{0:>2} NPS = {1}".format(jj, speeds[index]))

    # All Benchmarks should match
    if len(set(benches)) != 1:
        print("Error: Non-Deterministic Results!")
        sys.exit()

    # Final reporting of bench and average speeds
    print("\nBench for {0} is {1}".format(sys.argv[1], benches[0]))
    print("Speed for {0} is {1}".format(sys.argv[1], int(sum(speeds) / len(speeds))))
