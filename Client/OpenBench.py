from __future__ import print_function

import ast, argparse, time, sys, platform, multiprocessing, hashlib
import shutil, subprocess, requests, zipfile, os, math, json

# Run from any location ...
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Argument Parsing ... <Server> <Threads> <?Compiler> <?UsePGO>
parser = argparse.ArgumentParser()
parser.add_argument('-U', '--username', help='Username', required=True)
parser.add_argument('-P', '--password', help='Password', required=True)
parser.add_argument('-S', '--server', help='Server Address', required=True)
parser.add_argument('-T', '--threads', help='# of Threads', required=True)
parser.add_argument('-C', '--compiler', help='Compiler Name', required=True)
parser.add_argument('-O', '--profile', help='Use PGO Builds', required=False, default=False)
arguments = parser.parse_args()

# Client Parameters
USERNAME = arguments.username
PASSWORD = arguments.password
SERVER   = arguments.server
THREADS  = int(arguments.threads)
COMPILER = arguments.compiler
PROFILE  = arguments.profile

# Windows treated seperatly from Linux
IS_WINDOWS = platform.system() == 'Windows'

# Server wants to identify different machines
OS_NAME = platform.system() + ' ' + platform.release()

# Server tracks machines by IDs, which are saved
# locally once assigned. Regesitering a machine is
# not a problem, but creates junk in the database
try:
    with open('machine.txt') as fin:
        MACHINE_ID = int(fin.readlines()[0])
except:
    MACHINE_ID = None
    print('<Warning> Machine unregistered, will register with Server')

# Solution taken from Fishtest
def killProcess(process):
    try:
        # process.kill doesn't kill subprocesses on Windows
        if IS_WINDOWS: subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
        else: process.kill()
        process.wait()
        process.stdout.close()
    except:
        pass

def getNameAsExe(program):
    if IS_WINDOWS: return program + '.exe'
    return program

def getFile(source, outname):

    # Read a file from the given source and save it locally
    print('Downloading : {0}'.format(source))
    request = requests.get(url=source, stream=True)
    with open(outname, 'wb') as fout:
        for chunk in request.iter_content(chunk_size=1024):
            if chunk: fout.write(chunk)
        fout.flush()

def getCoreFiles():

    # Ask the server where the core files are saved
    request = requests.get(SERVER + '/getFiles/')
    location = request.content.decode('utf-8')

    # Download the proper cutechess program, and a dll if needed
    if IS_WINDOWS:
        if not os.path.isfile('cutechess.exe'):
            getFile(location + 'cutechess-windows.exe', 'cutechess.exe')
        if not os.path.isfile('Qt5Core.dll'):
            getFile(location +'cutechess-qt5core.dll', 'Qt5Core.dll')
    else:
        if not os.path.isfile('cutechess'):
            getFile(location + 'cutechess-linux', 'cutechess')
            os.system('chmod 777 cutechess')

def getEngine(data):

    name      = data['sha']
    source    = data['source']
    exe       = getNameAsExe(name)
    unzipname = source.split('/')[-3] + '-' + source.split('/')[-1].replace('.zip', '')

    # Don't redownload an engine we already have
    if os.path.isfile('Engines/' + exe):
        return

    # Log the fact that we are setting up a new engine
    print('\nSETTING UP ENGINE')
    print('Engine      :', data['name'])
    print('Commit      :', data['sha'])
    print('Source      :', source)

    # Extract and delete the zip file
    getFile(source, name + '.zip')
    with zipfile.ZipFile(name + '.zip') as data:
        data.extractall('tmp')
    os.remove(name + '.zip')

    # Build Engine using provided gcc and PGO flags
    buildEngine(exe, unzipname)

    # Create the Engines directory if it does not exist
    if not os.path.isdir('Engines'):
        os.mkdir('Engines')

    # Move the compiled engine
    if os.path.isfile('tmp/{0}/src/{1}'.format(unzipname, exe)):
        os.rename('tmp/{0}/src/{1}'.format(unzipname, exe), 'Engines/{0}'.format(exe))

    elif os.path.isfile('tmp/{0}/src/{1}'.format(unzipname, name)):
        os.rename('tmp/{0}/src/{1}'.format(unzipname, name), 'Engines/{0}'.format(exe))

    # Cleanup the unzipped zip file
    shutil.rmtree('tmp')

def buildEngine(exe, unzipname):

    # Build a standard non-PGO binary
    if not PROFILE:
        subprocess.Popen(
            ['make', 'CC={0}'.format(COMPILER), 'EXE={0}'.format(exe)],
            cwd='tmp/{0}/src/'.format(unzipname)).wait()
        return

    # Build a profiled binary
    subprocess.Popen(
        ['make', 'CC={0} -fprofile-generate'.format(COMPILER), 'EXE={0}'.format(exe)],
        cwd='tmp/{0}/src/'.format(unzipname)).wait()

    # Run a bench to generate profiler data
    subprocess.Popen(
        ['tmp/{0}/src/{1}'.format(unzipname, exe), 'bench'],
        stdin=subprocess.PIPE,
        universal_newlines=True
    ).wait()

    # Build the final binary using the PGO data
    subprocess.Popen(
        ['make', 'CC={0} -fprofile-use'.format(COMPILER), 'EXE={0}'.format(exe)],
        cwd='tmp/{0}/src'.format(unzipname)).wait()

def getCutechessCommand(data, scalefactor):

    if IS_WINDOWS: exe = 'cutechess.exe'
    else:          exe = './cutechess'

    timecontrol = data['test']['timecontrol']

    # Parse X / Y + Z time controls
    if '/' in timecontrol and '+' in timecontrol:
        moves = timecontrol.split('/')[0]
        start, inc = map(float, timecontrol.split('/')[1].split('+'))
        start = round(start * scalefactor, 2)
        inc = round(inc * scalefactor, 2)
        timecontrol  = moves + '/' + str(start) + '+' + str(inc)

    # Parse X / Y time controls
    elif '/' in timecontrol:
        moves = timecontrol.split('/')[0]
        start = float(timecontrol.split('/')[1])
        start = round(start * scalefactor, 2)
        timecontrol = moves + '/' + str(start)

    # Parse X + Z time controls
    else:
        start, inc = map(float, timecontrol.split('+'))
        start = round(start * scalefactor, 2)
        inc = round(inc * scalefactor, 2)
        timecontrol = str(start) + '+' + str(inc)

    # Find Threads / Options for the Dev Engine
    tokens = data['test']['dev']['options'].split(' ')
    devthreads = int(tokens[0].split('=')[1])
    devoptions = ' option.'.join(['']+tokens)

    # Find Threads / Options for the Base Engine
    tokens = data['test']['base']['options'].split(' ')
    basethreads = int(tokens[0].split('=')[1])
    baseoptions = ' option.'.join(['']+tokens)

    # Finally, output the time control for the user
    print ('ORIGINAL  :', data['test']['timecontrol'])
    print ('SCALED    :', timecontrol)
    print ('')

    generalFlags = (
        '-repeat'
        ' -srand ' + str(int(time.time())) +
        ' -resign movecount=3 score=400'
        ' -draw movenumber=40 movecount=8 score=10'
        ' -concurrency ' + str(int(math.floor(THREADS / max(devthreads, basethreads)))) +
        ' -games 1000'
        ' -recover'
        ' -wait 10'
    )

    devflags = (
        '-engine'
        ' cmd=Engines/' + getNameAsExe(data['test']['dev']['sha']) +
        ' proto=' + data['test']['dev']['protocol'] +
        ' tc=' + timecontrol + devoptions
    )

    baseflags = (
        '-engine'
        ' cmd=Engines/' + getNameAsExe(data['test']['base']['sha']) +
        ' proto=' + data['test']['base']['protocol'] +
        ' tc=' + timecontrol + baseoptions
    )

    bookflags = (
        '-openings'
        ' file=' + data['test']['book']['name'] +
        ' format=pgn'
        ' order=random'
        ' plies=16'
    )

    return ' '.join([exe, generalFlags, devflags, baseflags, bookflags])

def singleCoreBench(name, outqueue):

    # Format file path because of Windows ....
    dir = os.path.join('Engines', getNameAsExe(name))

    # Last two lines should hold node count and NPS
    data = os.popen('{0} bench'.format(dir)).read()
    data = data.strip().split('\n')

    # Parse and dump results into queue
    bench = int(data[-2].split(':')[1])
    nps   = int(data[-1].split(':')[1])
    outqueue.put((bench, nps))

def getBenchSignature(engine):

    print ('\nRunning Benchmark for {0} on {1} cores'.format(engine['name'], THREADS))

    # Allow each process to send back completition times
    outqueue = multiprocessing.Queue()

    # Launch and wait for completion of one process for each core
    processes = []
    for f in range(THREADS):
        processes.append(
            multiprocessing.Process(
                target=singleCoreBench,
                args=(engine['sha'], outqueue,)))
    for p in processes: p.start()
    for p in processes: p.join()

    # Parse data and compute average speed
    data  = [outqueue.get() for f in range(THREADS)]
    bench = [f[0] for f in data]
    nps   = [f[1] for f in data]
    avg   = sum(nps) / len(nps)

    # All benches should be the same
    if (len(set(bench)) > 1):
        return (0, 0)

    # Log and return computed bench and speed
    print ('Bench for {0} is {1}'.format(engine['name'], bench[0]))
    print ('NPS   for {0} is {1}'.format(engine['name'], int(avg)))
    return (bench[0], avg)

def reportWrongBench(data, engine):

    # Server wants verification for reporting wrong benchs
    postdata = {
        'username'  : USERNAME,
        'password'  : PASSWORD,
        'engineid'  : engine['id'],
        'testid'    : data['test']['id']}
    return requests.post('{0}/wrongBench/'.format(SERVER), data=postdata).text

def reportNPS(data, nps):

    # Server wants verification for reporting nps counts
    try:
        postdata = {
            'nps'       : nps,
            'username'  : USERNAME,
            'password'  : PASSWORD,
            'machineid' : data['machine']['id']}
        return requests.post('{0}/submitNPS/'.format(SERVER), data=postdata).text
    except: print ('<Warning> Unable to reach server')

def reportResults(data, wins, losses, draws, crashes, timeloss):

    # Server wants verification for reporting nps counts
    try:
        postdata = {
            'wins'      : wins,
            'losses'    : losses,
            'draws'     : draws,
            'crashes'   : crashes,
            'timeloss'  : timeloss,
            'username'  : USERNAME,
            'password'  : PASSWORD,
            'machineid' : data['machine']['id'],
            'resultid'  : data['result']['id'],
            'testid'    : data['test']['id']}
        return requests.post('{0}/submitResults/'.format(SERVER), data=postdata).text
    except: print ('<Warning> Unable to reach server')

def completeWorkload(data):

    # Download and verify bench of dev engine
    getEngine(data['test']['dev'])
    devbench, devnps = getBenchSignature(data['test']['dev'])
    if devbench != int(data['test']['dev']['bench']):
        print ('<ERROR> Invalid Bench. Got {0} Expected {1}'.format(
            devbench, int(data['test']['dev']['bench'])))
        reportWrongBench(data, data['test']['dev'])
        return

    # Download and verify bench of base engine
    getEngine(data['test']['base'])
    basebench, basenps = getBenchSignature(data['test']['base'])
    if basebench != int(data['test']['base']['bench']):
        print ('<ERROR> Invalid Bench. Got {0} Expected {1}'.format(
            basebench, int(data['test']['base']['bench'])))
        reportWrongBench(data, data['test']['base'])
        return

    # Download and verify sha of the opening book
    print('\nVERIFYING OPENING BOOK')
    if not os.path.isfile(data['test']['book']['name']):
        getFile(data['test']['book']['source'], data['test']['book']['name'])
    with open(data['test']['book']['name']) as fin:
        digest = hashlib.sha256(fin.read().encode('utf-8')).hexdigest()
    print ('Correct SHA : {0}'.format(digest.upper()))
    print ('MY Book SHA : {0}'.format(data['test']['book']['sha'].upper()))
    if (digest != data['test']['book']['sha']):
        print ('<ERROR> Invalid SHA for {0}'.format(data['test']['book']['name']))
        sys.exit()

    # Compute and report CPU scaling factor
    avgnps = (devnps + basenps) / 2.0
    reportNPS(data, avgnps)
    scalefactor = int(data['test']['nps']) / avgnps
    print ('\nFACTOR    : {0}'.format(round(1 / scalefactor, 2)))

    # Compute and report cutechess-cli string
    command = getCutechessCommand(data, scalefactor)
    print(command)

    # Spawn cutechess process
    process = subprocess.Popen(
        command.split(),
        stdout=subprocess.PIPE
    )

    # Tracking results of each game
    crashes = timeloss = 0
    sent = [0, 0, 0]; score = [0, 0, 0]

    while True:

        # Grab the next line of cutechess output
        line = process.stdout.readline().strip().decode('ascii')
        if line != '': print(line)

        # Update the current score line
        if line.startswith('Score of'):
            chunks = line.split(':')
            chunks = chunks[1].split()
            score = list(map(int, chunks[0:5:2]))

        # Search for the end of the cutechess process
        if line.startswith('Finished match') or 'Elo difference' in line:
            killProcess(process)
            break

        # Parse engine crashes
        if 'disconnects' in line or 'connection stalls' in line:
            crashes += 1

        # Parse losses on time
        if 'on time' in line:
            timeloss += 1

        # Batch result updates
        if (sum(score) - sum(sent)) % 25 == 0 and score != sent:
            wins   = score[0] - sent[0]
            losses = score[1] - sent[1]
            draws  = score[2] - sent[2]
            if reportResults(data, wins, losses, draws, crashes, timeloss) == 'Stop':
                killProcess(process)
                break
            crashes = timeloss = 0
            sent = score[::]

    # One final result send before we exit just in case
    wins   = score[0] - sent[0]
    losses = score[1] - sent[1]
    draws  = score[2] - sent[2]
    reportResults(data, wins, losses, draws, crashes, timeloss)

if __name__ == '__main__':

    # Download cutechess and any .dlls needed
    getCoreFiles()

    # Each Workload request will send this data
    postdata = {
        'username'  : USERNAME,
        'password'  : PASSWORD,
        'threads'   : THREADS,
        'osname'    : OS_NAME,
        'machineid' : str(MACHINE_ID),
    }

    while True:

        try:
            # Request the information for the next workload
            request = requests.post('{0}/getWorkload/'.format(SERVER), data=postdata)

            # Response is a dictionary of information, 'None', or an erro
            data = request.content.decode('utf-8')

            # Server has nothing to run, ask again later
            if data == 'None':
                print ('<Warning> Server has no workloads for us')
                time.sleep(60)
                continue

            # Server was unable to authenticate us
            if data == 'Bad Credentials':
                print ('<ERROR> Invalid Login Credentials')
                sys.exit()

            # Server might reject our Machine ID
            if data == 'Bad Machine':
                print ('<ERROR> Bad Machine. Delete machine.txt')
                sys.exit()

            # Convert response into a data dictionary
            data = ast.literal_eval(data)

            # Update and save our assigned machine ID
            postdata['machineid'] = data['machine']['id']
            with open('machine.txt', 'w') as fout:
                fout.write(str(postdata['machineid']))

            # Update machine id in case ours was bad
            postdata['machineid'] = data['machine']['id']

            # Begin working on the games to be played
            completeWorkload(data)

        except Exception as error:
            print ('<ERROR> {0}'.format(str(error)))
            time.sleep(10)
