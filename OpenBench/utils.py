import math, requests, random

from django.utils import timezone
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
        machine = Machine()
        machine.owner = username
        machine.osname = osname
        machine.threads = int(threads)
        return machine

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
    results = list(results.filter(machine=machine))
    if results != []: return results[0]

    # Must make a new one for the machine
    machine.save()
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
            'booksource'    : FRAMEWORK_REPO_URL + 'raw/master/Books/' + test.bookname,
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

def update(request, user):

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

    # Updated stats for SPRT and ELO calculation
    swins = test.wins + wins
    slosses = test.losses + losses
    sdraws = test.draws + draws

    # New stats for the test
    sprt     = SPRT(swins, slosses, sdraws, test.elolower, test.eloupper)
    passed   = sprt > test.upperllr
    failed   = sprt < test.lowerllr
    finished = passed or failed

    # Updating times manually since .update() won't invoke
    updated = timezone.now()

    # Update total # of games played for the User
    Profile.objects.filter(user=user).update(
        games=F('games') + games,
        updated=updated
    )

    # Update last time we saw a result
    Machine.objects.filter(id=machineid).update(
        updated=updated
    )

    # Update for the new results
    Result.objects.filter(id=resultid).update(
        games=F('games') + games,
        wins=F('wins') + wins,
        losses=F('losses') + losses,
        draws=F('draws') + draws,
        crashes=F('crashes') + crashes,
        timeloss=F('timeloss') + timeloss,
        updated=updated
    )

    # Finally, update test data and flags
    Test.objects.filter(id=testid).update(
        games=F('games') + games,
        wins=F('wins') + wins,
        losses=F('losses') + losses,
        draws=F('draws') + draws,
        currentllr=sprt,
        passed=passed,
        failed=failed,
        finished=finished,
        updated=updated
    )

    # Signal to stop completed tests
    if finished: raise Exception()

def SPRT(wins, losses, draws, elo0, elo1):

    # Estimate drawelo out of sample. Return LLR = 0.0 if there are not enough
    # games played yet to compute an LLR. 0.0 will always be an active state
    if wins > 0 and losses > 0 and draws > 0:
        N = wins + losses + draws
        elo, drawelo = proba_to_bayeselo(float(wins)/N, float(draws)/N, float(losses)/N)
    else: return 0.00

    # Probability laws under H0 and H1
    p0win, p0draw, p0loss = bayeselo_to_proba(elo0, drawelo)
    p1win, p1draw, p1loss = bayeselo_to_proba(elo1, drawelo)

    # Log-Likelyhood Ratio
    return    wins * math.log(p1win  /  p0win) \
          + losses * math.log(p1loss / p0loss) \
          +  draws * math.log(p1draw / p0draw)

def bayeselo_to_proba(elo, drawelo):
    pwin  = 1.0 / (1.0 + math.pow(10.0, (-elo + drawelo) / 400.0))
    ploss = 1.0 / (1.0 + math.pow(10.0, ( elo + drawelo) / 400.0))
    pdraw = 1.0 - pwin - ploss
    return pwin, pdraw, ploss

def proba_to_bayeselo(pwin, pdraw, ploss):
    elo     = 200 * math.log10(pwin/ploss * (1-ploss)/(1-pwin))
    drawelo = 200 * math.log10((1-ploss)/ploss * (1-pwin)/pwin)
    return elo, drawelo

def erf_inv(x):
    a = 8*(math.pi-3)/(3*math.pi*(4-math.pi))
    y = math.log(1-x*x)
    z = 2/(math.pi*a) + y/2
    return math.copysign(math.sqrt(math.sqrt(z*z - y/a) - z), x)

def phi_inv(p):
    # Quantile function for the standard Gaussian law: probability -> quantile
    assert(0 <= p and p <= 1)
    return math.sqrt(2)*erf_inv(2*p-1)

def ELO(wins, losses, draws):

    def _elo(x):
        if x <= 0 or x >= 1: return 0.0
        return -400*math.log10(1/x-1)

    # win/loss/draw ratio
    N = wins + losses + draws;
    if N == 0: return (0, 0, 0)
    w = float(wins)  / N
    l = float(losses)/ N
    d = float(draws) / N

    # mu is the empirical mean of the variables (Xi), assumed i.i.d.
    mu = w + d/2

    # stdev is the empirical standard deviation of the random variable (X1+...+X_N)/N
    stdev = math.sqrt(w*(1-mu)**2 + l*(0-mu)**2 + d*(0.5-mu)**2) / math.sqrt(N)

    # 95% confidence interval for mu
    mu_min = mu + phi_inv(0.025) * stdev
    mu_max = mu + phi_inv(0.975) * stdev

    return (_elo(mu_min), _elo(mu), _elo(mu_max))
