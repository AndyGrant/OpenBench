import ast, argparse, time, sys, platform, multiprocessing
import shutil, subprocess, requests, zipfile, os, math, json

# Argument Parsing ... <Server> <Threads> <?Compiler> <?UsePGO>
parser = argparse.ArgumentParser()
parser.add_argument("-U", "--username", help="Username", required=True)
parser.add_argument("-P", "--password", help="Password", required=True)
parser.add_argument("-E", "--server", help="Server Address", required=True)
parser.add_argument("-T", "--threads", help="# of Threads", required=True)
parser.add_argument("-C", "--compiler", help="Compiler Name", required=True)
parser.add_argument("-O", "--profile", help="Use PGO Builds", required=False, default=False)
arguments = parser.parse_args()

# Client Parameters
USERNAME = arguments.username
PASSWORD = arguments.password
SERVER   = arguments.server
THREADS  = arguments.threads
COMPILER = arguments.compiler
PROFILE  = arguments.profile

# Windows treated seperatly from Linux
IS_WINDOWS = platform.system() == "Windows"

# Server wants to identify different machines
OS_NAME = platform.system() + " " + platform.release()

# Server tracks machines by IDs, which are saved
# locally once assigned. Regesitering a machine is
# not a problem, but creates junk in the database
try:
    with open("machine.txt") as fin:
        MACHINE_ID = int(fin.readlines()[0])
except:
    MACHINE_ID = None
    print("<Warning> Machine unregistered, will register with Server")

# Run from any location ...
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def killProcess(process):
    if IS_WINDOWS:
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
    else:
        os.system("pkill -TERM -P {0}".format(process.pid))

def getNameAsExe(program):
    if IS_WINDOWS: return program + ".exe"
    return program

def getFile(source, savedname):

    # Read a file from the given source and save it locally
    request = requests.get(url=source, stream=True)
    with open(savedname, "wb") as fout:
        for chunk in request.iter_content(chunk_size=1024):
            if chunk: fout.write(chunk)
        fout.flush()

def getCoreFiles(server):

    # Ask the server where the core files are saved
    request = requests.get(server + "/getFiles/")
    location = request.content.decode("utf-8")

    # Download the proper cutechess program, and a dll if needed
    if IS_WINDOWS:
        if not os.path.isfile("cutechess.exe"):
            getFile(location + "cutechess-windows.exe", "cutechess.exe")
        if not os.path.isfile("Qt5Core.dll"):
            getFile(location +"cutechess-qt5core.dll", "Qt5Core.dll")
    else:
        if not os.path.isfile("cutechess"):
            getFile(location + "cutechess-linux", "cutechess")
            os.system("chmod 777 cutechess")

def getEngine(data):

    isCandidate = "sha" in data

    if isCandidate:
        name = data["sha"]
        source = data["source"]
        exe = getNameAsExe(name)
        unzipname = source.split("/")[-3] + "-" + source.split("/")[-1].replace(".zip", "")

    else:
        name = unzipname = data["name"]
        source = data["source"] + name + ".zip"
        exe = getNameAsExe(name)

    # Don't redownload an engine we already have
    if os.path.isfile("Engines/" + exe):
        return

    # Log the fact that we are downloading a new engine
    print("\nEngine :", data["name"])
    print(  "Commit :", data["sha"])
    print(  "Source :", source)

    # Extract and delete the zip file
    getFile(source, name + ".zip")
    with zipfile.ZipFile(name + ".zip") as data:
        data.extractall("tmp")
    os.remove(name + ".zip")

    # Build Engine using provided gcc and PGO flags
    buildEngine(exe, unzipname)

    # Create the Engines directory if it does not exist
    if not os.path.isdir("Engines"):
        os.mkdir("Engines")

    # Move the compiled engine
    if os.path.isfile("tmp/{0}/src/{1}".format(unzipname, exe)):
        os.rename("tmp/{0}/src/{1}".format(unzipname, exe), "Engines/{0}".format(exe))

    elif os.path.isfile("tmp/{0}/src/{1}".format(unzipname, name)):
        os.rename("tmp/{0}/src/{1}".format(unzipname, name), "Engines/{0}".format(exe))

    # Cleanup the unzipped zip file
    shutil.rmtree("tmp")

def buildEngine(exe, unzipname):

    # Build a standard non-PGO binary
    if not USE_PROFILE:
        subprocess.Popen(
            ['make', 'CC={0}'.format(GCC_VERSION), 'EXE={0}'.format(exe)],
            cwd="tmp/{0}/src/".format(unzipname)).wait()
        return

    # Build a profiled binary
    subprocess.Popen(
        ['make', 'CC={0} -fprofile-generate'.format(GCC_VERSION), 'EXE={0}'.format(exe)],
        cwd="tmp/{0}/src/".format(unzipname)).wait()

    # Run a bench to generate profiler data
    subprocess.Popen(
        ["tmp/{0}/src/{1}".format(unzipname, exe), "bench"],
        stdin=subprocess.PIPE,
        universal_newlines=True
    ).wait()

    # Build the final binary using the PGO data
    subprocess.Popen(
        ['make', 'CC={0} -fprofile-use'.format(GCC_VERSION), 'EXE={0}'.format(exe)],
        cwd="tmp/{0}/src".format(unzipname)).wait()

def getCutechessCommand(cores, data, scalefactor):

    if IS_WINDOWS: exe = "cutechess.exe"
    else:          exe = "./cutechess"

    timecontrol     = data["enginetest"]["timecontrol"]

    # Parse X / Y + Z time controls
    if "/" in timecontrol and "+" in timecontrol:
        moves = timecontrol.split("/")[0]
        start, inc = map(float, timecontrol.split("/")[1].split("+"))
        start = round(start * scalefactor, 2)
        inc = round(inc * scalefactor, 2)
        tc  = moves + "/" + str(start) + "+" + str(inc)

    # Parse X / Y time controls
    elif "/" in timecontrol:

        moves = timecontrol.split("/")[0]
        start = float(timecontrol.split("/")[1])
        start = round(start * scalefactor, 2)
        tc = moves + "/" + str(start)

    # Parse X + Z time controls
    else:
        start, inc = map(float, timecontrol.split("+"))
        start = round(start * scalefactor, 2)
        inc = round(inc * scalefactor, 2)
        tc = str(start) + "+" + str(inc)

    print ("ORIGINAL  :", timecontrol)
    print ("SCALED    :", tc)
    print ("")

    generalFlags = (
        "-repeat"
        " -srand " + str(int(time.time())) +
        " -resign movecount=3 score=400"
        " -draw movenumber=40 movecount=8 score=10"
        " -concurrency " + str(floor(cores / data["enginetest"]["threads"])) +
        " -games 1000"
        " -recover"
        " -wait 10"
    )

    candidateflags = (
        "-engine"
        " cmd=Engines/" + getNameAsExe(data["enginetest"]["test"]["sha"]) +
        " proto=uci" +
        " tc=" + tc +
        " option.Hash=" + str(data["enginetest"]["hashsize"]) +
        " option.Threads=" + str(data["enginetest"]["threads"])
    )

    opponentflags = (
        "-engine"
        " cmd=Engines/" + getNameAsExe(data["enginetest"]["base"]["sha"]) +
        " proto=uci" +
        " tc=" + tc +
        " option.Hash=" + str(data["enginetest"]["hashsize"]) +
        " option.Threads=" + str(data["enginetest"]["threads"])
    )

    bookflags = (
        "-openings"
        " file=book.pgn"
        " format=pgn"
        " order=random"
        " plies=16"
    )

    return " ".join([exe, generalFlags, candidateflags, opponentflags, bookflags])

def singleCoreBench(name, outqueue):

    # Format file path because of Windows ....
    dir = os.path.join("Engines", getNameAsExe(name))

    # Last two lines should hold node count and NPS
    data = os.popen("{0} bench 13 |tail -2".format(dir)).read()
    data = data.strip().split("\n")

    # Parse and dump results into queue
    bench = int(data[0].split(":")[1])
    nps   = int(data[1].split(":")[1])
    outqueue.put((bench, nps))

def getBenchSignature(engine, cores):

    print ("Running Benchmark for {0} on {1} cores".format(engine["name"], cores))

    # Allow each process to send back completition times
    outqueue = multiprocessing.Queue()

    # Launch and wait for completion of one process for each core
    processes = []
    for f in range(cores):
        processes.append(
            multiprocessing.Process(
                target=singleCoreBench,
                args=(engine["sha"], outqueue,)))
    for p in processes: p.start()
    for p in processes: p.join()

    data  = [outqueue.get() for f in range(cores)]
    bench = [f[0] for f in data]
    nps   = [f[1] for f in data]
    avg   = sum(nps) / len(nps)

    if (len(set(bench)) > 1):
        return (0, 0)

    print ("Bench for {0} is {1}".format(engine["name"], bench[0]))
    print ("NPS   for {0} is {1}\n".format(engine["name"], int(avg)))
    return (bench[0], avg)

def completeWorkload(server, cores, data):

    # Download both engines in the matchup and the root engine
    getEngine(data["enginetest"]["test"])
    getEngine(data["enginetest"]["base"])
    print ("")

    # Verify the bench of the test engine
    testbench, testnps = getBenchSignature(data["enginetest"]["test"], cores)
    if testbench != int(data["enginetest"]["test"]["bench"]):
        print (testbench, int(data["enginetest"]["test"]["bench"]))
        enginetestid = int(data["enginetest"]["id"])
        requests.get(server + "/wrongbench/{0}/".format(enginetestid))
        return

    # Verify the bench of the base engine
    basebench, basenps = getBenchSignature(data["enginetest"]["base"], cores)
    if basebench != int(data["enginetest"]["base"]["bench"]):
        print (basebench, int(data["enginetest"]["base"]["bench"]))
        enginetestid = int(data["enginetest"]["id"])
        requests.get(server + "/wrongbench/{0}/".format(enginetestid))
        return

    scalefactor = 2650000 / ((testnps + basenps) / 2)
    print ("FACTOR    : {0}".format(round(1 / scalefactor, 2)))

    command = getCutechessCommand(cores, data, scalefactor)
    print(command)

    process = subprocess.Popen(
        command,
        shell=not IS_WINDOWS,
        stdout=subprocess.PIPE
    )

    # Cutechess uses W / L / D
    score = [0, 0, 0]
    sent  = [0, 0, 0]

    while True:

        # Grab the next line of cutechess output
        line = process.stdout.readline().strip().decode("ascii")

        # Skip over empty lines
        if line != "":
            print(line)

        # Update the current score line
        if line.startswith("Score of"):
            chunks = line.split(":")
            chunks = chunks[1].split()
            score = list(map(int, chunks[0:5:2]))

        # Search for the end of the cutechess process
        if line.startswith("Finished match") or "Elo difference" in line:
            killProcess(process)
            break

        # Send results in sets of 25
        if (sum(score) - sum(sent)) % 25 == 0 and sum(score) - sum(sent) > 0:
            try:
                r = requests.post(url=server+"/submitResults/", data={
                    "enginetestid" : data["enginetest"]["id"],
                    "wins"         : score[0] - sent[0],
                    "draws"        : score[2] - sent[2],
                    "losses"       : score[1] - sent[1],
                })
                sent = score[::]

                if r.text == "Stop":
                    killProcess(process)
                    break
            except: pass

    # Send any leftover results before exiting
    while True:
        try:
            requests.post(url=server+"/submitResults/", data={
                "enginetestid" : data["enginetest"]["id"],
                "wins"         : score[0] - sent[0],
                "draws"        : score[2] - sent[2],
                "losses"       : score[1] - sent[1],
            })
            return
        except: pass

if __name__ == "__main__":

    # Download cutechess and any .dlls needed
    getCoreFiles(SERVER)

    # Each Workload request will send this data
    data = {
        "username"  : USERNAME,
        "password"  : PASSWORD,
        "threads"   : THREADS,
        "osname"    : OS_NAME,
        "machineid" : str(MACHINE_ID),
    }

    while True:

        # Request the information for the next workload
        request = requests.post("{0}/getWorkload/".format(SERVER), data=data)

        # Response is a dictionary of information, "None", or an erro
        response = request.content.decode("utf-8")

        # Server has nothing to run, ask again later
        if response == "None":
            print("<Warning> Server has no workloads for us")
            time.sleep(60)
            continue

        # Server was unable to authenticate us
        if response == "Bad Credentials":
            print("<Error> Invalid Login Credentials")
            sys.exit()

        # Server might reject our Machine ID
        if response == "Bad Machine":
            print("<Error> Bad Machine. Delete machine.txt")
            sys.exit()

        # Convert response into a data dictionary
        response = ast.literal_eval(response)

        # Update and save our assigned machine ID
        data["machineid"] = response["machine"]["id"]
        with open("machine.txt", "w") as fout:
            fout.write(str(data["machineid"]))

        # Update machine id in case ours was bad
        data["machineid"] = response["machine"]["id"]

        print (response)

        sys.exit(0)