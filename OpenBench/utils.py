import math, requests, random

from OpenBench.config import *
from OpenBench.models import Engine, Profile, Machine, Result, Test


def getSourceLocation(branch, repo):

    try:
        target = repo.replace('github.com', 'api.github.com/repos')
        target = target + 'branches/' + branch
        data   = requests.get(target).json()
        source = repo + 'archive/' + data['commit']['commit']['tree']['sha'] + '.zip'
        sha    = data['commit']['sha']
        return (sha, source)

    except:
        raise Exception('Unable to find branch ({0})'.format(branch))

def newTest(request):

    test = Test() # New Test, saved only after parsing
    test.author = request.user.username

    # Extract Development Fields
    devname     = request.POST['devbranch']
    devbench    = int(request.POST['devbench'])
    devprotocol = request.POST['devprotocol']

    # Extract Base Fields
    basename     = request.POST['basebranch']
    basebench    = int(request.POST['basebench'])
    baseprotocol = request.POST['baseprotocol']

    # Extract test configuration
    test.source      = request.POST['source']
    test.devoptions  = request.POST['devoptions']
    test.baseoptions = request.POST['baseoptions']
    test.bookname    = request.POST['bookname']
    test.timecontrol = request.POST['timecontrol']
    test.priority    = int(request.POST['priority'])
    test.throughput  = int(request.POST['throughput'])
    test.elolower    = float(request.POST['elolower'])
    test.eloupper    = float(request.POST['eloupper'])
    test.alpha       = float(request.POST['alpha'])
    test.beta        = float(request.POST['beta'])

    # Compute LLR cutoffs
    test.lowerllr = math.log(test.beta / (1.0 - test.alpha))
    test.upperllr = math.log((1.0 - test.beta) / test.alpha)

    # Build or fetch the Development version
    devsha, devsource = getSourceLocation(devname, test.source)
    test.dev = getEngine(devname, devsource, devprotocol, devsha, devbench)

    # Build or fetch the Base version
    basesha, basesource = getSourceLocation(basename, test.source)
    test.base = getEngine(basename, basesource, baseprotocol, basesha, basebench)

    # Track # of tests by this user
    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    # Nothing seems to have gone wrong
    test.save()
    return test

def getEngine(name, source, protocol, sha, bench):

    # Engine may already exist, which is okay
    try: return Engine.objects.get(name=name, source=source, protocol=protocol, sha=sha, bench=bench)
    except: pass

    # Build new Engine
    return Engine.objects.create(
            name=name, source=source,
            protocol=protocol, sha=sha, bench=bench)

def getMachine(machineid, username, osname, threads):

    # Client has no saved machine ID, make a new machine
    if machineid == 'None':
        return Machine.objects.create(owner=username, osname=osname, threads=int(threads))

    # Fetch and verify the claimed machine ID
    machine = Machine.objects.get(id=machineid)
    assert machine.owner == username
    assert machine.osname == osname

    # Update to reflect new worload
    machine.threads = int(threads)
    machine.mnps = 0.00
    machine.save()
    return machine

def getWorkload(machine):

    # Get a list of all active tests
    tests = Test.objects.filter(finished=False)
    tests = tests.filter(deleted=False)
    tests = list(tests.filter(approved=True))

    # No tests, error out and let views handle it
    if len(tests) == 0: raise Exception('None')

    options = [] # Highest priority with acceptable threads

    # Find our options for workloads
    for test in tests:

        # Find Threads for the Dev Engine
        tokens = test.devoptions.split(' ')
        devthreads = int(tokens[0].split('=')[1])

        # Find Threads for the Base Engine
        tokens = test.baseoptions.split(' ')
        basethreads = int(tokens[0].split('=')[1])

        # Minimum threads to support Dev & Base
        threadcnt = max(devthreads, basethreads)

        # Empty list or higher priority found for workable test
        if (options == [] or test.priority > highest) and threadcnt <= machine.threads:
            highest = test.priority
            options = [test]

        # New workable test with the same priority
        elif options != [] and test.priority == highest and threadcnt <= machine.threads:
            options.append(test)

    # Sum of throughputs, for weighted randomness
    total = sum([test.throughput for test in options])
    target = random.randrange(0, total)

    # Finally, select our test with the weighted target
    while True:

        # Found test within the target throughput
        if target < options[0].throughput:
            return options[0]

        # Drop the test from selection
        target -= options[0].throughput
        options = options[1:]

def getResult(machine, test):

    # Can find an existing result by test and machine
    results = Result.objects.filter(test=test)
    results = list(Result.objects.filter(machine=machine))
    if results != []: return results[0]

    # Must make a new one for the machine
    return Result.objects.create(test=test, machine=machine)

def workloadDictionary(machine, result, test):

    # Worker will send back the id of each model for ease of
    # updating. Worker needs test information, as well as the
    # specification for both engines. Group the dev and base
    # options with the coressponding engine, for easy usage
    return {
        'machine' : { 'id'  : machine.id, },
        'result'  : { 'id'  : result.id, },
        'test' : {
            'id'            : test.id,
            'bookname'      : test.bookname,
            'booksource'    : FRAMEWORK_REPO_URL + '/raw/master/Books/',
            'timecontrol'   : test.timecontrol,
            'dev' : {
                'id'        : test.dev.id,
                'name'      : test.dev.name,
                'source'    : test.dev.source,
                'protocol'  : test.dev.protocol,
                'sha'       : test.dev.sha,
                'bench'     : test.dev.bench,
                'options'   : test.devoptions,
            },
            'base' : {
                'id'        : test.base.id,
                'name'      : test.base.name,
                'source'    : test.base.source,
                'protocol'  : test.base.protocol,
                'sha'       : test.base.sha,
                'bench'     : test.base.bench,
                'options'   : test.baseoptions,
            },
        },
    }
