import math, requests, random

from OpenBench.models import Engine, Profile, Machine, Test

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

def newEngine(name, source, protocol, sha, bench):

    # Engine may already exist, which is okay
    try: return Engine.objects.get(sha=sha)
    except: pass

    # Build new Engine
    engine = Engine()
    engine.name = name
    engine.source = source
    engine.protocol = protocol
    engine.sha = sha
    engine.bench = bench
    engine.save()
    return engine

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
    test.dev = newEngine(devname, devsource, devprotocol, devsha, devbench)

    # Build or fetch the Base version
    basesha, basesource = getSourceLocation(basename, test.source)
    test.base = newEngine(basename, basesource, baseprotocol, basesha, basebench)

    # Track # of tests by this user
    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    # Nothing seems to have gone wrong
    test.save()
    return test

def getMachine(machineid, username, osname, threads):

    # Machine does not exist, make a new one
    if machineid == 'None':
        machine = Machine()
        machine.owner = username
        machine.osname = osname
        machine.threads = threads
        machine.mnps = 0.00
        machine.save()
        return machine

    # Verify the selected machine is the user's
    machine = Machine.objects.get(id=machineid)
    assert machine.owner == username
    assert machine.osname == osname
    machine.threads = threads
    machine.mnps = 0.00
    machine.save()
    return machine

def getWorkload(machine):

    # Get a list of all active tests
    tests = Test.objects.filter(finished=False)
    tests = tests.filter(deleted=False)
    tests = list(tests.filter(approved=True))

    # No tests, error out and let views handle it
    if len(tests) == 0: raise Exception('ANone')

    options = [] # Highest priority with acceptable threads

    # Find our options for workloads
    for test in tests:

        # Find Threads for the Dev Engine
        tokens = test.devoptions.split(' ')
        devthreads = tokens[0].split('=')[1]

        # Find Threads for the Base Engine
        tokens = test.baseoptions.split(' ')
        basethreads = tokens[0].split('=')[1]

        # Machines need at to support Dev & Base
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

def getResults(machine, test):
    pass

def workloadDictionary(profile, machine, result, test):
    
    # Worker will send back the id of each model for ease of
    # updating. Worker needs test information, as well as the
    # specification for both engines. Group the dev and base
    # options with the coressponding engine, for easy usage
    return {
        'profile' : { 'id'  : profile.id, },
        'machine' : { 'id'  : machine.id, },
        'result'  : { 'id'  : result.id, },        
        'test' : {
            'id'            : test.id,
            'bookname'      : test.bookname,
            'booksource'    : FRAMEWORK_REPO_URL + '/raw/master/Books/'
            'timecontrol'   : test.timecontrol,
            'dev' : { 
                'name'      : test.dev.name,
                'source'    : test.dev.source,
                'protocol'  : test.dev.protocol,
                'sha'       : test.dev.sha,
                'bench'     : test.dev.bench,
                'options'   : test.devoptions,
            },
            'base' : {
                'name'      : test.base.name,
                'source'    : test.base.source,
                'protocol'  : test.base.protocol,
                'sha'       : test.base.sha,
                'bench'     : test.base.bench,
                'options'   : test.baseoptions,
            },
        },
    }
