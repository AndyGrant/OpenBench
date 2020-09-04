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

import math, re, requests, random, datetime, os

import OpenBench.models, OpenBench.stats

import django.utils.timezone

from django.utils import timezone
from django.db.models import F
from django.contrib.auth import authenticate

from OpenBench.config import *
from OpenBench.models import Engine, Profile, Machine, Result, Test


def pathjoin(*args):
    return "/".join([f.lstrip("/").rstrip("/") for f in args]) + "/"

def extractOption(options, option):

    match = re.search('(?<={0}=")[^"]*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=\')[^\']*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=)[^ ]*'.format(option), options)
    if match: return match.group()


def getPendingTests():
    pending = OpenBench.models.Test.objects.filter(approved=False)
    pending = pending.exclude(finished=True)
    pending = pending.exclude(deleted=True)
    return pending.order_by('-creation')

def getActiveTests():
    active = OpenBench.models.Test.objects.filter(approved=True)
    active = active.exclude(finished=True)
    active = active.exclude(deleted=True)
    return active.order_by('-priority', '-currentllr')

def getCompletedTests():
    completed = OpenBench.models.Test.objects.filter(finished=True)
    completed = completed.exclude(deleted=True)
    return completed.order_by('-updated')


def getRecentMachines(minutes=15):
    target = datetime.datetime.utcnow()
    target = target.replace(tzinfo=django.utils.timezone.utc)
    target = target - datetime.timedelta(minutes=minutes)
    return Machine.objects.filter(updated__gte=target)

def getMachineStatus(username=None):

    machines = getRecentMachines()

    if username != None:
        machines = machines.filter(user__username=username)

    return "{0} Machines ".format(len(machines)) + \
           "{0} Threads ".format(sum([f.threads for f in machines])) + \
           "{0} MNPS ".format(round(sum([f.threads * f.mnps for f in machines]), 2))

def getPaging(content, page, url, pagelen=25):

    start = max(0, pagelen * (page - 1))
    end   = min(content.count(), pagelen * page)
    count = 1 + math.ceil(content.count() / pagelen)

    part1 = list(range(1, min(4, count)))
    part2 = list(range(page - 2, page + 1))
    part3 = list(range(page + 1, page + 3))
    part4 = list(range(count - 3, count + 1))

    pages = part1 + part2 + part3 + part4
    pages = [f for f in pages if f >= 1 and f <= count]
    pages = list(set(pages))
    pages.sort()

    final = []
    for f in range(len(pages) - 1):
        final.append(pages[f])
        if pages[f] != pages[f+1] - 1:
            final.append('...')

    context = {
        "url" : url, "page" : page, "pages" : final,
        "prev" : max(1, page - 1), "next" : max(1, min(page + 1, count - 1)),
    }

    return start, end, context


def getEngine(source, name, sha, bench, protocol):

    engine = Engine.objects.filter(
        name=name, source=source,
        protocol=protocol, sha=sha, bench=bench)

    if engine.first() != None:
        return engine.first()

    return Engine.objects.create(
        name=name, source=source,
        protocol=protocol, sha=sha, bench=bench)

def getBranch(request, errors, name):

    branch = request.POST['{0}branch'.format(name)]
    bysha = bool(re.search('[0-9a-fA-F]{40}', branch))
    url = 'commits' if bysha else 'branches'

    repo = request.POST['source']
    target = repo.replace('github.com', 'api.github.com/repos')
    target = pathjoin(target, url, branch).rstrip('/')


    # Avoid leaking our credentials to other sites
    if not target.startswith('https://api.github.com/'):
        errors.append('OpenBench may only reach Github\'s API')
        return (None, None, None, None)

    # Check for a (User, Token) credentials file
    if os.path.exists('credentials'):
        with open('credentials') as fin:
            user, token = fin.readlines()[0].rstrip().split()
            auth = requests.auth.HTTPBasicAuth(user, token)
    else: auth = None


    try:
        data = requests.get(target, auth=auth).json()
        data = data if bysha else data['commit']

    except:
        lookup = 'Commit Sha' if bysha else 'Branch'
        errors.append('{0} {1} could not be found'.format(lookup, branch))
        return (None, None, None, None)

    treeurl = data['commit']['tree']['sha'] + '.zip'
    source = pathjoin(repo, 'archive', treeurl).rstrip('/')

    try:
        message = data['commit']['message'].replace(',', '').upper()
        bench = re.search('(BENCH|NODES)[ :=]+[0-9]+', message)
        if bench: bench = int(re.search('[0-9]+', bench.group()).group())
        else: bench = int(request.POST['{0}bench'.format(name)])

    except:
        errors.append('Unable to parse a Bench for {0}'.format(branch))
        return (None, None, None, None)

    return (source, branch, data['sha'], bench)

def verifyNewTest(request):

    errors = []

    def verifyInteger(field, fieldName):
        try: int(request.POST[field])
        except: errors.append('{0} is not an Integer'.format(fieldName))

    def verifyFloating(field, fieldName):
        try: float(request.POST[field])
        except: errors.append('{0} is not a Floating Point'.format(fieldName))

    def verifyLessThan(field, fieldName, value, valueName):
        if not float(request.POST[field]) < value:
            errors.append('{0} is not less than {1}'.format(fieldName, valueName))

    def verifyGreaterThan(field, fieldName, value, valueName):
        if not float(request.POST[field]) > value:
            errors.append('{0} is not greater than {1}'.format(fieldName, valueName))

    def verifyOptions(field, option, fieldName):
        if extractOption(request.POST[field], option) == None:
            errors.append('{0} was not found as an option for {1}'.format(option, fieldName))
        elif int(extractOption(request.POST[field], option)) < 1:
            errors.append('{0} needs to be at least 1 for {1}'.format(option, fieldName))

    def verifyConfiguration(field, fieldName, parent):
        if request.POST[field] not in OpenBench.config.OPENBENCH_CONFIG[parent].keys():
            errors.append('{0} was not found in the configuration'.format(fieldName))

    def verifyGithubLink(field, fieldName):
        if request.POST[field] and not request.POST[field].startswith('https://github.com/'):
            errors.append('{0} must be located on a Github URL'.format(fieldName))

    verifications = [
        (verifyInteger, 'priority', 'Priority'),
        (verifyInteger, 'throughput', 'Throughput'),
        (verifyFloating, 'elolower', 'Elo Lower'),
        (verifyFloating, 'eloupper', 'Elo Upper'),
        (verifyFloating, 'alpha', 'Alpha'),
        (verifyFloating, 'beta', 'Beta'),
        (verifyLessThan, 'alpha', 'Alpha', 1.00, '1'),
        (verifyLessThan, 'beta', 'Beta', 1.00, '1'),
        (verifyGreaterThan, 'alpha', 'Alpha', 0.00, '0'),
        (verifyGreaterThan, 'beta', 'beta', 0.00, '0'),
        (verifyGreaterThan, 'throughput', 'Throughput', 0, '0'),
        (verifyOptions, 'devoptions', 'Threads', 'Dev Options'),
        (verifyOptions, 'devoptions', 'Hash', 'Dev Options'),
        (verifyOptions, 'baseoptions', 'Threads', 'Base Options'),
        (verifyOptions, 'baseoptions', 'Hash', 'Base Options'),
        (verifyConfiguration, 'enginename', 'Engine', 'engines'),
        (verifyConfiguration, 'bookname', 'Book', 'books'),
        (verifyGithubLink, 'devnetwork', 'Dev Network'),
        (verifyGithubLink, 'basenetwork', 'Base Network'),
    ]

    for verification in verifications:
        try: verification[0](*verification[1:])
        except: pass

    return errors

def createNewTest(request):

    errors = verifyNewTest(request)
    if errors != []: return None, errors

    devinfo = getBranch(request, errors, 'dev')
    baseinfo = getBranch(request, errors, 'base')
    protocol  = OPENBENCH_CONFIG['engines'][request.POST['enginename']]['proto']
    if errors != []: return None, errors

    test = Test()
    test.author      = request.user.username
    test.engine      = request.POST['enginename']
    test.source      = request.POST['source']
    test.devoptions  = request.POST['devoptions']
    test.baseoptions = request.POST['baseoptions']
    test.devnetwork  = request.POST['devnetwork']
    test.basenetwork = request.POST['basenetwork']
    test.bookname    = request.POST['bookname']
    test.timecontrol = request.POST['timecontrol']
    test.priority    = int(request.POST['priority'])
    test.throughput  = int(request.POST['throughput'])
    test.elolower    = float(request.POST['elolower'])
    test.eloupper    = float(request.POST['eloupper'])
    test.alpha       = float(request.POST['alpha'])
    test.beta        = float(request.POST['beta'])
    test.lowerllr    = math.log(test.beta / (1.0 - test.alpha))
    test.upperllr    = math.log((1.0 - test.beta) / test.alpha)
    test.dev         = getEngine(*devinfo, protocol)
    test.base        = getEngine(*baseinfo, protocol)
    test.save()

    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    return test, None


def getMachine(machineid, user, osname, threads):

    # Create a new Machine if needed
    if machineid == 'None':
        return Machine(user=user, osname=osname, threads=threads)

    # Fetch and verify the requested Machine
    try: machine = Machine.objects.get(id=int(machineid))
    except: return 'Bad Machine'
    if machine.user != user: return 'Bad Machine'
    if machine.osname != osname: return 'Bad Machine'

    # Update the Machine's running status
    machine.threads = threads
    machine.mnps = 0.00
    return machine

def getResult(test, machine):

    # Try to find an already existing Result
    results = Result.objects.filter(test=test)
    results = list(results.filter(machine=machine))
    if results != []: return results[0]

    # Create a new Result if none is found
    return Result(test=test, machine=machine)

def getWorkload(user, request):

    # Extract worker information
    machineid = request.POST['machineid']
    osname    = request.POST['osname'   ]
    threads   = request.POST['threads'  ]

    # If we don't get a Machine back, there was an error
    machine = getMachine(machineid, user, osname, int(threads))
    if type(machine) == str: return machine

    # Compare supported Machines vs Existing
    supported = request.POST['supported'].split()
    existing  = OPENBENCH_CONFIG['engines'].keys()

    # Filter only to active tests
    tests = Test.objects.filter(finished=False)
    tests = tests.filter(deleted=False)
    tests = tests.filter(approved=True)

    # Remove tests that this Machine cannot complete
    for engine in existing:
        if engine not in supported:
            tests = tests.exclude(engine=engine)

    # If we don't get a Test back, there was an error
    test = selectWorkload(tests, machine)
    if type(test) == str: return test

    # If we don't get a Result back, there was an error
    result = getResult(test, machine)
    if type(result) == str: return result

    # Success. Update the Machine's status and save everything
    machine.workload = test; machine.save(); result.save()
    return str(workloadDictionary(test, result, machine))

def selectWorkload(tests, machine):

    options = [] # Tests which this Machine may complete

    for test in tests:

        # Skip tests which the Machine lacks the threads to complete
        devthreads  = int(extractOption(test.devoptions, 'Threads'))
        basethreads = int(extractOption(test.baseoptions, 'Threads'))
        if max(devthreads, basethreads) > machine.threads: continue

        # First Test or a higher priority Test
        if not options or test.priority > highest:
            highest = test.priority; options = [test]

        # Another Test with an equal priority
        elif options and test.priority == highest:
            options.append(test)

    if not options: return 'None'

    target = random.randrange(sum([t.throughput for t in options]))
    while True: # Select a random test used weighted randomness
        if target < options[0].throughput: return options[0]
        target -= options[0].throughput; options = options[1:]

def workloadDictionary(test, result, machine):

    # Convert the workload into a Dictionary to be used by the Client.
    # The Client must know his Machine ID, his Result ID, and his Test
    # ID. Also, all information about the Test and the associated engines

    return {

        'machine' : { 'id'  : machine.id },

        'result'  : { 'id'  : result.id },

        'test' : {

            'id'            : test.id,
            'nps'           : OPENBENCH_CONFIG['engines'][test.engine]['nps'],
            'build'         : OPENBENCH_CONFIG['engines'][test.engine]['build'],
            'book'          : OPENBENCH_CONFIG['books'][test.bookname],
            'timecontrol'   : test.timecontrol,
            'engine'        : test.engine,
            'dev' : {
                'id'        : test.dev.id,      'name'      : test.dev.name,
                'source'    : test.dev.source,  'protocol'  : test.dev.protocol,
                'sha'       : test.dev.sha,     'bench'     : test.dev.bench,
                'options'   : test.devoptions,
                'network'   : test.devnetwork,
            },

            'base' : {
                'id'        : test.base.id,     'name'      : test.base.name,
                'source'    : test.base.source, 'protocol'  : test.base.protocol,
                'sha'       : test.base.sha,    'bench'     : test.base.bench,
                'options'   : test.baseoptions,
                'network'   : test.basenetwork,
            },
        },
    }


def updateTest(request, user):

    # New results from the Worker
    wins     = int(request.POST['wins'])
    losses   = int(request.POST['losses'])
    draws    = int(request.POST['draws'])
    crashes  = int(request.POST['crashes'])
    timeloss = int(request.POST['timeloss'])
    games    = wins + losses + draws

    # Worker knows where to save the results
    machineid = int(request.POST['machineid'])
    resultid  = int(request.POST['resultid'])
    testid    = int(request.POST['testid'])

    # Prevent updating a finished test
    test = Test.objects.get(id=testid)
    if test.finished or test.deleted:
        return 'Stop'

    # Compute a new LLR for the updated results
    swins   = test.wins   + wins
    slosses = test.losses + losses
    sdraws  = test.draws  + draws
    WLD     = (swins, slosses, sdraws)
    sprt    = OpenBench.stats.SPRT(*WLD, test.elolower, test.eloupper)

    # Check for an H0 or H1 being accepted
    passed   = sprt > test.upperllr
    failed   = sprt < test.lowerllr
    finished = passed or failed

    # Update total games played by the Player
    Profile.objects.filter(user=user).update(games=F('games') + games)
    Profile.objects.get(user=user).save()

    # Update the datetime in the Machine
    Machine.objects.get(id=machineid).save()

    # Update individual Result entry for the Player
    Result.objects.filter(id=resultid).update(
        games   = F('games')   + games,   wins     = F('wins'    ) + wins,
        losses  = F('losses')  + losses,  draws    = F('draws'   ) + draws,
        crashes = F('crashes') + crashes, timeloss = F('timeloss') + timeloss,
    )

    # Update the overall test with the new data
    Test.objects.filter(id=testid).update(
        games  = F('games' ) + games,  wins  = F('wins' ) + wins,
        losses = F('losses') + losses, draws = F('draws') + draws,
        currentllr=sprt, passed=passed, failed=failed, finished=finished,
    )

    # Force a refresh of the updated field when finished
    if finished: Test.objects.get(id=testid).save()

    return ['None', 'Stop'][finished]
