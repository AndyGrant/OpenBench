import math, requests, random

from django.db.models import F
from django.contrib.auth import authenticate

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

def update(request):

    # Log the user in to verify
    user = authenticate(
        username=request.POST['username'],
        password=request.POST['password'])

    # Parse the data from the worker
    wins     = int(request.POST['wins'])
    losses   = int(request.POST['losses'])
    draws    = int(request.POST['draws'])
    crashes  = int(request.POST['crashes'])
    timeloss = int(request.POST['timeloss'])
    games    = wins + losses + draws

    # Parse the various IDs sent back
    machineid = int(request.POST['machineid'])
    resultid  = int(request.POST['resultid'])
    testid    = int(request.POST['testid'])

    # Don't update an finished, deleted, or unappoved test
    test = Test.objects.get(id=testid)
    if test.finished or test.deleted or not test.approved:
        raise Exception()

    # New stats for the test
    elo      = ELO(test)
    sprt     = SPRT(test)
    passed   = sprt > test.upperllr
    failed   = sprt < test.lowerllr
    finished = passed or failed

    # Update total # of games played for the User
    Profile.objects.filter(user=user).update(games=F('games') + games)

    # Just force an update to Machine.update
    Machine.objects.filter(id=machineid).update()

    # Update for the new results
    Result.objects.filter(id=resultid).update(
        games=F('games') + games,
        wins=F('wins') + wins,
        losses=F('losses') + losses,
        draws=F('draws') + draws,
        crashes=F('crashes') + crashes,
        timeloss=F('timeloss') + timeloss,
    )

    # Finally, update test data and flags
    Test.objects.filter(id=testid).update(
        games=F('games') + games,
        wins=F('wins') + wins,
        losses=F('losses') + losses,
        draws=F('draws') + draws,
        currentllr=sprt,
        elo=elo,
        passed=passed,
        failed=failed,
        finished=finished
    )

    # Signal to stop completed tests
    if finished: raise Exception()

def ELO(test):
    w = test.wins
    d = test.draws
    l = test.losses
    n = w + d + l
    if n == 0: return 0.0
    s = w + d / 2.0
    p = s / n
    if p == 0.0 or p == 1.0: return 0.0
    return -400.0 * math.log10(1 / p - 1)

def bayeselo_to_proba(elo, drawelo):
    pwin  = 1.0 / (1.0 + math.pow(10.0, (-elo + drawelo) / 400.0))
    ploss = 1.0 / (1.0 + math.pow(10.0, ( elo + drawelo) / 400.0))
    pdraw = 1.0 - pwin - ploss
    return pwin, pdraw, ploss

def proba_to_bayeselo(pwin, pdraw, ploss):
    elo     = 200 * math.log10(pwin/ploss * (1-ploss)/(1-pwin))
    drawelo = 200 * math.log10((1-ploss)/ploss * (1-pwin)/pwin)
    return elo, drawelo

def SPRT(test):

    # Estimate drawelo out of sample. Return LLR = 0.0 if there are not enough
    # games played yet to compute an LLR. 0.0 will always be an active state
    if test.wins > 0 and test.losses > 0 and test.draws > 0:
        N = test.wins + test.losses + test.draws
        elo, drawelo = proba_to_bayeselo(float(test.wins)/N, float(test.draws)/N, float(test.losses)/N)
    else: return 0.00

    # Probability laws under H0 and H1
    p0win, p0draw, p0loss = bayeselo_to_proba(test.elolower, drawelo)
    p1win, p1draw, p1loss = bayeselo_to_proba(test.eloupper, drawelo)

    # Log-Likelyhood Ratio
    return    test.wins * math.log(p1win  /  p0win) \
          + test.losses * math.log(p1loss / p0loss) \
          +  test.draws * math.log(p1draw / p0draw)