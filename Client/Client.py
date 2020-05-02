# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

from __future__ import print_function

import argparse, ast, hashlib, json, math, multiprocessing, os
import platform, re, requests, shutil, subprocess, sys, time, zipfile


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

HTTP_TIMEOUT          = 30    # Timeout in seconds for requests
WORKLOAD_TIMEOUT      = 60    # Timeout when there is no work
ERROR_TIMEOUT         = 60    # Timeout when an error is thrown
GAMES_PER_CONCURRENCY = 32    # Total games to play per concurrency
SAVE_PGN_FILES        = False # Auto-save PGN output for engine pairings
AUTO_DELETE_ENGINES   = True  # Delete Engines that are over 24hrs old

CUSTOM_SETTINGS = {
    'Ethereal'  : { 'args' : [] }, # Configuration for Ethereal
    'Laser'     : { 'args' : [] }, # Configuration for Laser
    'Weiss'     : { 'args' : [] }, # Configuration for Weiss
    'Demolito'  : { 'args' : [] }, # Configuration for Demolito
    'Rubichess' : { 'args' : [] }, # Configuration for RubiChess
    'FabChess'  : { 'args' : [] }, # Configuration for FabChess
};

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


# Treat Windows and Linux systems differently
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX   = platform.system() != 'Windows'

COMPILERS = {} # Mapping of Engines to Compilers


def addExtension(name):
    return name + ["", ".exe"][IS_WINDOWS]

def pathjoin(*args):

    # Join a set of URL paths while maintaining the correct
    # format of "/"'s between each part of the URL's pathway

    args = [f.lstrip("/").rstrip("/") for f in args]
    return "/".join(args) + "/"

def killCutechess(cutechess):

    try:
        # Manually kill process trees for Windows
        if IS_WINDOWS:
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(cutechess.pid)])
            cutechess.wait()
            cutechess.stdout.close()

        # Subprocesses close nicely on Linux
        if IS_LINUX:
            cutechess.kill()
            cutechess.wait()
            cutechess.stdout.close()

    except KeyboardInterrupt: sys.exit()
    except Exception as error: pass

def cleanupEnginesDirectory():

    SECONDS_PER_DAY = 60 * 60 * 24;

    for file in os.listdir('Engines/'):
        if time.time() - os.path.getmtime('Engines/{0}'.format(file)) > SECONDS_PER_DAY:
            os.remove('Engines/{0}'.format(file))
            print ("[NOTE] Deleted old engine", file)


def getCutechess(server):

    # Ask the server where the core files are saved
    source = requests.get(
        pathjoin(server, 'clientGetFiles'),
        timeout=HTTP_TIMEOUT).content.decode('utf-8')

    # Windows workers need the cutechess.exe and the Qt5Core dll.
    # Linux workers need cutechess and the libcutechess SO.
    # Make sure Linux binaries are set to be executable.

    if IS_WINDOWS and not os.path.isfile('cutechess.exe'):
        getFile(pathjoin(source, 'cutechess-windows.exe'), 'cutechess.exe')

    if IS_WINDOWS and not os.path.isfile('Qt5Core.dll'):
        getFile(pathjoin(source, 'cutechess-qt5core.dll'), 'Qt5Core.dll')

    if IS_LINUX and not os.path.isfile('cutechess'):
        getFile(pathjoin(source, 'cutechess-linux'), 'cutechess')
        os.system('chmod 777 cutechess')

    if IS_LINUX and not os.path.isfile('libcutechess.so.1'):
        getFile(pathjoin(source, 'libcutechess.so.1'), 'libcutechess.so.1')

def getCompilationSettings(server):

    # Get a dictionary of engine -> compilers
    data = requests.get(
        pathjoin(server, 'clientGetBuildInfo'),
        timeout=HTTP_TIMEOUT).content.decode('utf-8')
    data = ast.literal_eval(data)

    for engine, compilers in data.items():
        for compiler in compilers:

            # Compilers may require a specific version
            if '>=' in compiler:
                compiler, version = compiler.split('>=')
                version = tuple(map(int, version.split('.')))
            else: compiler = compiler; version = (0, 0, 0)

            # Try to execute the compiler from the command line
            try: stdout, stderr = subprocess.Popen(
                    [compiler, '--version'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                ).communicate()
            except OSError: continue

            # Parse the version number reported by the compiler
            stdout = stdout.decode('utf-8')
            match = re.search(r'[0-9]+\.[0-9]+\.[0-9]+', stdout).group()
            actual = tuple(map(int, match.split('.')))

            # Compiler was not sufficient
            if actual < version: continue

            # Compiler was sufficient
            COMPILERS[engine] = {
                'compiler' : compiler, 'version' : match,
                'default' : compiler == compilers[0]
            }; break

    # Report each engine configuration we can build for
    for engine in [engine for engine in data.keys() if engine in COMPILERS]:
        compiler, version = COMPILERS[engine]['compiler'], COMPILERS[engine]['version']
        print("Found {0} {1} for {2}".format(compiler, version, engine))

    # Report each engine configuration we cannot build for
    for engine in [engine for engine in data.keys() if engine not in COMPILERS]:
        print("Unable to find compiler for {0}".format(engine))


def getFile(source, output):

    # Download the source file
    print('Downloading {0}'.format(source))
    request = requests.get(url=source, stream=True, timeout=HTTP_TIMEOUT)

    # Write the file out chunk by chunk
    with open(output, 'wb') as fout:
        for chunk in request.iter_content(chunk_size=1024):
            if chunk: fout.write(chunk)
        fout.flush()

def getAndUnzipFile(source, name, output):

    # Download and extract .zip file
    getFile(source, name)
    with zipfile.ZipFile(name) as fin:
        fin.extractall(output)

    # Cleanup by deleting the .zip
    os.remove(name)


def getMachineID():

    # Check if the machine is registered
    if os.path.isfile('machine.txt'):
        with open('machine.txt', 'r') as fin:
            return fin.readlines()[0]

    # Notify user when the machine is new
    print('[NOTE] Machine Is Unregistered')
    return 'None'

def getEngine(data, engine):

    print('Engine {0}'.format(data['test']['engine']))
    print('Branch {0}'.format(engine['name']))
    print('Commit {0}'.format(engine['sha']))
    print('Source {0}'.format(engine['source']))

    # Extract the zipfile to /tmp/ for future processing
    # Format: https://github.com/User/Engine/archive/SHA.zip
    tokens = engine['source'].split('/')
    unzipname = '{0}-{1}'.format(tokens[-3], tokens[-1].replace('.zip', ''))
    getAndUnzipFile(engine['source'], '{0}.zip'.format(engine['name']), 'tmp')
    pathway = pathjoin('tmp/{0}/'.format(unzipname), data['test']['build']['path'])

    # Basic make assumption and an EXE= hook
    command = ['make', 'EXE={0}'.format(engine['name'])]

    # Use a CC= hook if we are using the non-default compiler
    if not COMPILERS[data['test']['engine']]['default']:
        command.append('CC={0}'.format(COMPILERS[data['test']['engine']]['compiler']))

    # Add any other custom compilation options if we have them
    if data['test']['engine'] in CUSTOM_SETTINGS:
        command.extend(CUSTOM_SETTINGS[data['test']['engine']]['args'])

    # Build the engine. If something goes wrong with the
    # compilation process, we will figure this out later on
    subprocess.Popen(command, cwd=pathway).wait(); print("")

    # Move the binary to the /Engines/ directory
    output = '{0}{1}'.format(pathway, engine['name'])
    destination = addExtension(pathjoin('Engines', engine['sha']).rstrip('/'))

    # Check to see if the compiler included a file extension or not
    if os.path.isfile(output): os.rename(output, destination)
    if os.path.isfile(output + '.exe'): os.rename(output + '.exe', destination)

    # Cleanup the zipfile directory
    shutil.rmtree('tmp')

def getCutechessCommand(arguments, data, nps):

    # Parse options for Dev
    tokens = data['test']['dev']['options'].split(' ')
    devthreads = int(tokens[0].split('=')[1])
    devoptions = ' option.'.join(['']+tokens)

    # Parse options for Base
    tokens = data['test']['base']['options'].split(' ')
    basethreads = int(tokens[0].split('=')[1])
    baseoptions = ' option.'.join(['']+tokens)

    # Ensure .exe extension on Windows
    devCommand = addExtension(data['test']['dev']['sha'])
    baseCommand = addExtension(data['test']['base']['sha'])

    # Scale the time control for this machine's speed
    timecontrol = computeAdjustedTimecontrol(arguments, data, nps)

    # Find max concurrency for the given testing conditions
    concurrency = int(math.floor(int(arguments.threads) / max(devthreads, basethreads)))

    # Check for an FRC/Chess960 opening book
    if "FRC" in data['test']['book']['name'].upper(): variant = 'fischerandom'
    elif "960" in data['test']['book']['name'].upper(): variant = 'fischerandom'
    else: variant = 'standard'

    # General Cutechess options
    generalflags = '-repeat -recover -srand {0} -resign {1} -draw {2} -wait 10'.format(
        int(time.time()), 'movecount=3 score=400', 'movenumber=40 movecount=8 score=10'
    )

    # Options about tournament conditions
    setupflags = '-variant {0} -concurrency {1} -games {2}'.format(
        variant, concurrency, concurrency * GAMES_PER_CONCURRENCY
    )

    # Options for the Dev Engine
    devflags = '-engine dir=Engines/ cmd=./{0} proto={1} tc={2}{3} name={4}'.format(
        devCommand, data['test']['dev']['protocol'], timecontrol, devoptions,
        '{0}-{1}'.format(data['test']['engine'], data['test']['dev']['name'])
    )

    # Options for the Base Engine
    baseflags = '-engine dir=Engines/ cmd=./{0} proto={1} tc={2}{3} name={4}'.format(
        baseCommand, data['test']['base']['protocol'], timecontrol, baseoptions,
        '{0}-{1}'.format(data['test']['engine'], data['test']['base']['name'])
    )

    # Options for opening selection
    bookflags = '-openings file=Books/{0} format={1} order=random plies=16'.format(
        data['test']['book']['name'], data['test']['book']['name'].split('.')[-1]
    )

    # Save PGN files if requested as Engine-Dev_vs_Engine-Base
    if SAVE_PGN_FILES:
        bookflags += ' -pgnout PGNs/{0}-{1}_vs_{0}-{2}'.format(
            data['test']['engine'], data['test']['dev']['name'], data['test']['base']['name'])

    # Combine all flags and add the cutechess program callout
    options = ' '.join([generalflags, setupflags, devflags, baseflags, bookflags])
    if IS_WINDOWS: return 'cutechess.exe {0}'.format(options), concurrency
    if IS_LINUX: return './cutechess {0}'.format(options), concurrency


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

def computeSingleThreadedBenchmark(engine, outqueue):

    try:

        # Launch the engine and run a benchmark
        pathway = addExtension(os.path.join('Engines', engine).rstrip('/'))
        stdout, stderr = subprocess.Popen(
            './{0} bench'.format(pathway).split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).communicate()

        # Parse output streams for the benchmark data
        bench, speed = parseStreamOutput(stdout)
        if bench is None or speed is None:
            bench, speed = parseStreamOutput(stderr)
        outqueue.put((int(bench), int(speed)))

    # Missing file, unable to run, failed to compile, or some other
    # error. Force an exit by sending back a null bench and nps value
    except Exception as error:
        print("[ERROR] {0}".format(str(error)))
        outqueue.put((0, 0))

def computeMultiThreadedBenchmark(arguments, engine):

    # Log number of benchmarks being spawned for the given engine
    print('Running {0}x Benchmarks for {1}'.format(arguments.threads, engine['name']))

    # Each computeSingleThreadedBenchmark() reports to this Queue
    outqueue = multiprocessing.Queue()

    # Spawn a computeSingleThreadedBenchmark() for each thread
    processes = [
        multiprocessing.Process(
            target=computeSingleThreadedBenchmark,
            args=(engine['sha'], outqueue,)
        ) for f in range(int(arguments.threads))
    ]

    # Launch every benchmark
    for process in processes:
        process.start()

    # Wait for each benchmark
    for process in processes:
        process.join()

    # Extract the benches and nps counts from each worker
    data  = [outqueue.get() for f in range(int(arguments.threads))]
    bench = [int(f[0]) for f in data]
    speed = [int(f[1]) for f in data]
    avg   = sum(speed) / len(speed)

    # Flag an error if there were different benches
    if (len(set(bench)) > 1): return (0, 0)

    # Log and return computed bench and speed
    print ('Bench for {0} is {1}'.format(engine['name'], bench[0]))
    print ('speed for {0} is {1}\n'.format(engine['name'], int(avg)))
    return (bench[0], avg)

def computeAdjustedTimecontrol(arguments, data, nps):

    # Scale and report the nodes per second
    factor = int(data['test']['nps']) / nps
    timecontrol = data['test']['timecontrol'];
    reportNodesPerSecond(arguments, data, nps)

    # Parse X / Y + Z time controls
    if '/' in timecontrol and '+' in timecontrol:
        moves = timecontrol.split('/')[0]
        start, inc = map(float, timecontrol.split('/')[1].split('+'))
        start = round(start * factor, 2)
        inc = round(inc * factor, 2)
        return moves + '/' + str(start) + '+' + str(inc)

    # Parse X / Y time controls
    elif '/' in timecontrol:
        moves = timecontrol.split('/')[0]
        start = float(timecontrol.split('/')[1])
        start = round(start * factor, 2)
        return moves + '/' + str(start)

    # Parse X + Z time controls
    else:
        start, inc = map(float, timecontrol.split('+'))
        start = round(start * factor, 2)
        inc = round(inc * factor, 2)
        return str(start) + '+' + str(inc)


def verifyOpeningBook(data):

    # Fetch the opening book if we don't have it
    print('\nFetching and Verifying Opening Book')
    if not os.path.isfile('Books/{0}'.format(data['name'])):
        source = '{0}.zip'.format(data['source'])
        name = '{0}.zip'.format(data['name'])
        getAndUnzipFile(source, name, 'Books/')

    # Verify data integrity with a hash
    with open('Books/{0}'.format(data['name'])) as fin:
        content = fin.read().encode('utf-8')
        sha = hashlib.sha256(content).hexdigest()

    # Log the SHA verification
    print('Correct SHA {0}'.format(data['sha']))
    print('Download SHA {0}\n'.format(sha))

    # Signal for error when SHAs do not match
    return data['sha'] == sha

def verifyEngine(arguments, data, engine):

    # Download the engine if we do not already have it
    pathway = addExtension(pathjoin('Engines', engine['sha']).rstrip('/'))
    if not os.path.isfile(pathway): getEngine(data, engine)

    # Run a group of benchmarks in parallel in order to better scale NPS
    # values for this worker. We obtain a bench and average NPS value
    bench, nps = computeMultiThreadedBenchmark(arguments, engine)

    # Check for an invalid bench. Signal to the Client and the Server
    if bench != int(engine['bench']):
        reportWrongBenchmark(arguments, data, engine, bench)
        raise Exception('Invalid Bench. Got {0} Expected {1}'.format(bench, engine['bench']))

    # Return a valid bench or otherwise return None
    return nps if bench == int(engine['bench']) else None


def reportWrongBenchmark(arguments, data, engine, bench):


    data = {
        'username' : arguments.username, 'testid' : data['test']['id'],
        'password' : arguments.password, 'machineid' : data['machine']['id'],
        'correct'  : engine['bench']   , 'wrong'  : bench,
        'engine'   : engine['name'],
    }

    url = pathjoin(arguments.server, 'clientWrongBench')
    data = requests.post(url, data=data, timeout=HTTP_TIMEOUT).text
    if data == 'Bad Machine': raise Exception('Bad Machine')

def reportNodesPerSecond(arguments, data, nps):


    data = {
        'username'  : arguments.username, 'machineid' : data['machine']['id'],
        'password'  : arguments.password, 'nps'       : nps,
    }

    url = pathjoin(arguments.server, 'clientSubmitNPS')
    data = requests.post(url, data=data, timeout=HTTP_TIMEOUT).text
    if data == 'Bad Machine': raise Exception('Bad Machine')

def reportEngineError(arguments, data, line):

    pairing = line.split('(')[1].split(')')[0]
    white, black = pairing.split(' vs ')

    error = line.split('{')[1].rstrip().rstrip('}')
    error = error.replace('White', '-'.join(white.split('-')[1:]).rstrip())
    error = error.replace('Black', '-'.join(black.split('-')[1:]).rstrip())

    data = {
        'username' : arguments.username, 'testid'    : data['test']['id'],
        'password' : arguments.password, 'machineid' : data['machine']['id'],
        'error'    : error,
    }

    url = pathjoin(arguments.server, 'clientSubmitError')
    data = requests.post(url, data=data, timeout=HTTP_TIMEOUT).text
    if data == 'Bad Machine': raise Exception('Bad Machine')

def reportResults(arguments, data, wins, losses, draws, crashes, timelosses):

    data = {
        'username'  : arguments.username,    'wins'      : wins,
        'password'  : arguments.password,    'losses'    : losses,
        'machineid' : data['machine']['id'], 'draws'     : draws,
        'resultid'  : data['result']['id'],  'crashes'   : crashes,
        'testid'    : data['test']['id'],    'timeloss'  : timelosses,
    }

    url = pathjoin(arguments.server, 'submitResults')
    try: return requests.post(url, data=data, timeout=HTTP_TIMEOUT).text
    except KeyboardInterrupt: sys.exit()
    except: print('[NOTE] Unable To Reach Server'); return "Unable"


def processCutechess(arguments, data, cutechess, concurrency):

    # Tracking for game results
    crashes = timelosses = 0
    score = [0, 0, 0]; sent = [0, 0, 0]
    errors = ['on time', 'disconnects', 'connection stalls', 'illegal']

    while True:

        # Output the next line or quit when the pipe closes
        line = cutechess.stdout.readline().strip().decode('ascii')
        if line != '': print(line)
        else: cutechess.wait(); return

        # Updated timeloss/crash counters
        timelosses += 'on time' in line
        crashes    += 'disconnects' in line
        crashes    += 'connection stalls' in line

        # Report any engine errors to the server
        for error in errors:
            if error in line:
                reportEngineError(arguments, data, line)

        # Parse updates to scores
        if line.startswith('Score of'):

            # Format: Score of test vs base: W - L - D  [0.XXX] N
            score = list(map(int, line.split(':')[1].split()[0:5:2]))

            # After every `concurrency` results, update the server
            if (sum(score) - sum(sent)) % concurrency == 0:

                # Look only at the delta since last report
                WLD = [score[f] - sent[f] for f in range(3)]
                status = reportResults(arguments, data, *WLD, crashes, timelosses)

                # Check for the task being aborted
                if status.upper() == 'STOP':
                    killCutechess(cutechess)
                    return

                # If we fail to update the server, hold onto the results
                if status.upper() != 'UNABLE':
                    crashes = timelosses = 0
                    sent = score[::]

def processWorkload(arguments, data):

    # Verify and possibly download the opening book
    if not verifyOpeningBook(data['test']['book']): sys.exit()

    # Download, Verify, and Benchmark each engine. If we are unable
    # to obtain a valid bench for an engine, we exit this workload
    devnps = verifyEngine(arguments, data, data['test']['dev'])
    basenps = verifyEngine(arguments, data, data['test']['base'])

    avgnps = (devnps + basenps) / 2
    command, concurrency = getCutechessCommand(arguments, data, avgnps)
    print("Launching Cutechess\n{0}\n".format(command))

    cutechess = subprocess.Popen(command.split(), stdout=subprocess.PIPE)
    processCutechess(arguments, data, cutechess, concurrency)

def completeWorkload(workRequestData, arguments):

    # Get the next workload
    data = requests.post(
        pathjoin(arguments.server, 'clientGetWorkload'),
        data=workRequestData, timeout=HTTP_TIMEOUT).content.decode('utf-8')

    # Check for an empty workload
    if data == 'None':
        print('\n[NOTE] Server Has No Work')
        time.sleep(WORKLOAD_TIMEOUT)
        return

    # Kill process if unable to login
    if data == 'Bad Credentials':
        print('\n[ERROR] Invalid Login Credentials')
        sys.exit()

    # Bad machines will be registered again
    if data == 'Bad Machine':
        workRequestData['machineid'] = 'None'
        print('\n[NOTE] Invalid Machine ID')
        return

    # Convert response into a dictionary
    data = ast.literal_eval(data)

    # Update machine ID in case we got registered
    if workRequestData['machineid'] != data['machine']['id']:
        workRequestData['machineid'] = data['machine']['id']
        with open('machine.txt', 'w') as fout:
            fout.write(str(workRequestData['machineid']))

    # Handle the actual workload's completion
    processWorkload(arguments, data)


def main():

    # Use OpenBench.py's path as the base pathway
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Ensure we have our usual file folder structure
    if not os.path.isdir('Engines'): os.mkdir('Engines')
    if not os.path.isdir('Books'  ): os.mkdir('Books'  )
    if not os.path.isdir('PGNs'   ): os.mkdir('PGNs'   )

    # Expect a Username, Password, Server, and Threads value
    p = argparse.ArgumentParser()
    p.add_argument('-U', '--username', help='Username', required=True)
    p.add_argument('-P', '--password', help='Password', required=True)
    p.add_argument('-S', '--server', help='Server Address', required=True)
    p.add_argument('-T', '--threads', help='Number of Threads', required=True)
    arguments = p.parse_args()

    # Make sure we have cutechess installed
    getCutechess(arguments.server)

    # Determine how we will compile engines
    print("\nChecking for installed Compilers",)
    getCompilationSettings(arguments.server)

    # All workload requests must be tied to a user and a machine.
    # We also pass a thread count to inform the server what tests this
    # machine can handle. We pass the osname in order to register machines.
    # We pass a space seperated string of the engines we are able to compile.
    workRequestData = {
        'machineid' : getMachineID(),
        'username'  : arguments.username,
        'password'  : arguments.password,
        'threads'   : arguments.threads,
        'osname'    : '{0} {1}'.format(platform.system(), platform.release()),
        'supported' : ' '.join(COMPILERS.keys()),
    };

    # Continually pull down and complete workloads
    while True:
        if AUTO_DELETE_ENGINES: cleanupEnginesDirectory()
        try: completeWorkload(workRequestData, arguments)
        except KeyboardInterrupt: sys.exit()
        except Exception as error:
            print ('[ERROR] {0}'.format(str(error)))
            time.sleep(ERROR_TIMEOUT)


if __name__ == '__main__':
    main()
