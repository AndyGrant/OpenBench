import multiprocessing, os, subprocess, sys, time

def singleCoreBench(engine, outqueue):

    # Launch the bench and wait for results
    stdout, stderr = subprocess.Popen(
        "./{0} bench".format(engine).split(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()

    # Parse bench and speed. The final two lines, respectivly
    data = stdout.decode("ascii").strip().split("\n")
    outqueue.put((int(data[-2].split()[-1]), int(data[-1].split()[-1])))

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

    # Launch eat singleCoreBench()
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
