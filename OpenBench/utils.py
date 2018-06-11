from OpenBench.models import Engine, Profile, Machine, Test

import math, requests

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
    devsha, devsource = getSourceLocation(devname,  request.POST['source'])
    test.dev = newEngine(devname,  devsource,  devprotocol,  devsha,  devbench)

    # Build or fetch the Base version
    basesha, basesource = getSourceLocation(basename, request.POST['source'])
    test.base = newEngine(basename, basesource, baseprotocol, basesha, basebench)

    # Track # of tests by this user
    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    # Nothing seems to have gone wrong
    test.save()
    return test