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

import math, re, requests, random, datetime, os, json

import OpenBench.models, OpenBench.stats

import django.utils.timezone

from django.utils import timezone
from django.db.models import F
from django.contrib.auth import authenticate

from OpenBench.config import *
from OpenBench.models import Engine, Profile, Machine, Result, Test, Network


def pathjoin(*args):
    return "/".join([f.lstrip("/").rstrip("/") for f in args]) + "/"

def extractOption(options, option):

    match = re.search('(?<={0}=")[^"]*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=\')[^\']*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=)[^ ]*'.format(option), options)
    if match: return match.group()

def parseTimeControl(time_control):

    # Searching for X/Y+Z time controls
    pattern = '(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
    results = re.search(pattern, time_control)
    moves, base, inc = results.group('moves', 'base', 'inc')

    # Strip the trailing and leading symbols
    moves = None if moves == '' else moves.rstrip('/')
    inc   = 0.0  if inc   is None else inc.lstrip('+')

    # Format the time control for cutechess
    if moves is None: return '%.1f+%.2f' % (float(base), float(inc))
    return '%d/%.1f+%.2f' % (int(moves), float(base), float(inc))


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


def getRecentMachines(minutes=5):
    target = datetime.datetime.utcnow()
    target = target.replace(tzinfo=django.utils.timezone.utc)
    target = target - datetime.timedelta(minutes=minutes)
    return Machine.objects.filter(updated__gte=target)

def getMachineStatus(username=None):

    machines = getRecentMachines()

    if username != None:
        machines = machines.filter(user__username=username)

    return ": {0} Machines / ".format(len(machines)) + \
           "{0} Threads / ".format(sum([f.threads for f in machines])) + \
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


def getEngine(source, name, sha, bench):

    engine = Engine.objects.filter(name=name, source=source, sha=sha, bench=bench)
    if engine.first() != None: return engine.first()
    return Engine.objects.create(name=name, source=source, sha=sha, bench=bench)

def getBranch(request, errors, name):

    branch = request.POST['{0}branch'.format(name)]
    bysha  = bool(re.search('[0-9a-fA-F]{40}', branch))
    url    = 'commits' if bysha else 'branches'

    repo   = request.POST['source']
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

    try: # Fetch data from the Github API
        data = requests.get(target, auth=auth).json()
        data = data if bysha else data['commit']

    except: # Unable to connect for whatever reason
        lookup = 'Commit Sha' if bysha else 'Branch'
        errors.append('{0} {1} could not be found'.format(lookup, branch))
        return (None, None, None, None)

    treeurl = data['commit']['tree']['sha'] + '.zip'
    source  = pathjoin(repo, 'archive', treeurl).rstrip('/')

    try: # Use the provided Bench if there is one
        bench = int(request.POST['{0}bench'.format(name)])
        return (source, branch, data['sha'], bench)
    except: pass

    try: # Fallback to try to parse the Bench from the commit
        message = data['commit']['message']
        benches = re.findall('(?:BENCH|NODES)[ :=]+([0-9,]+)', message, re.IGNORECASE)
        bench   = int(benches[-1].replace(',', ''))
        return (source, branch, data['sha'], bench)

    except: # Neither method found a viable Bench
        errors.append('Unable to parse a Bench for {0}'.format(branch))
        return (None, None, None, None)

def verifyNewTest(request):

    errors = []

    def verifyInteger(field, fieldName):
        try: int(request.POST[field])
        except: errors.append('{0} is not an Integer'.format(fieldName))

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

    def verifyTimeControl(field, fieldName):
        try: parseTimeControl(request.POST[field])
        except: errors.append('{0} is not a parsable {1}'.format(request.POST[field], fieldName))

    verifications = [
        (verifyInteger, 'priority', 'Priority'),
        (verifyInteger, 'throughput', 'Throughput'),
        (verifyGreaterThan, 'throughput', 'Throughput', 0, '0'),
        (verifyOptions, 'devoptions', 'Threads', 'Dev Options'),
        (verifyOptions, 'devoptions', 'Hash', 'Dev Options'),
        (verifyOptions, 'baseoptions', 'Threads', 'Base Options'),
        (verifyOptions, 'baseoptions', 'Hash', 'Base Options'),
        (verifyConfiguration, 'enginename', 'Engine', 'engines'),
        (verifyConfiguration, 'bookname', 'Book', 'books'),
        (verifyTimeControl, 'timecontrol', 'Time Control'),
    ]

    for verification in verifications:
        try: verification[0](*verification[1:])
        except: pass

    return errors

def createNewTest(request):

    errors = []; verifyNewTest(request)
    if errors != []: return None, errors

    devinfo = getBranch(request, errors, 'dev')
    baseinfo = getBranch(request, errors, 'base')
    if errors != []: return None, errors

    test = Test()
    test.author      = request.user.username
    test.engine      = request.POST['enginename']
    test.test_mode   = request.POST['test_mode']
    test.source      = request.POST['source']
    test.devoptions  = request.POST['devoptions'].rstrip(' ')
    test.baseoptions = request.POST['baseoptions'].rstrip(' ')
    test.devnetwork  = request.POST['devnetwork']
    test.basenetwork = request.POST['basenetwork']
    test.bookname    = request.POST['bookname']
    test.timecontrol = parseTimeControl(request.POST['timecontrol'])
    test.priority    = int(request.POST['priority'])
    test.throughput  = int(request.POST['throughput'])
    test.syzygy_adj  = request.POST['syzygy_adj']
    test.syzygy_wdl  = request.POST['syzygy_wdl']

    if request.POST['test_mode'] == 'SPRT':
        test.elolower = float(request.POST['bounds'].split(',')[0].lstrip('['))
        test.eloupper = float(request.POST['bounds'].split(',')[1].rstrip(']'))
        test.alpha    = float(request.POST['confidence'].split(',')[1].rstrip(']'))
        test.beta     = float(request.POST['confidence'].split(',')[0].lstrip('['))
        test.lowerllr = math.log(test.beta / (1.0 - test.alpha))
        test.upperllr = math.log((1.0 - test.beta) / test.alpha)

    if request.POST['test_mode'] == 'GAMES':
        test.max_games = int(request.POST['max_games'])

    if request.POST['devnetwork']:
        test.devnetname = Network.objects.get(sha256=request.POST['devnetwork']).name

    if request.POST['basenetwork']:
        test.basenetname = Network.objects.get(sha256=request.POST['basenetwork']).name

    test.dev         = getEngine(*devinfo)
    test.base        = getEngine(*baseinfo)
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

    # Check to make sure we have a potential workload
    tests = get_valid_workloads(machine, request)
    if not tests: return 'None'

    # Select from valid workloads and create a Result object
    test = select_workload(machine, tests)
    result = getResult(test, machine)

    # Success. Update the Machine's status and save everything
    machine.workload = test; machine.save(); result.save()
    return str(workload_to_dictionary(test, result, machine))


# Purely Helper functions for getWorkload()

def get_valid_workloads(machine, request):

    # Skip finished tests
    tests = Test.objects.filter(finished=False)
    tests = tests.filter(deleted=False).filter(approved=True)

    # Skip engines that the Machine cannot build
    for engine in OPENBENCH_CONFIG['engines'].keys():
        if engine not in request.POST['supported'].split():
            tests = tests.exclude(engine=engine)

    # Skip engines that the Machine cannot run
    for engine, data in OPENBENCH_CONFIG['engines'].items():
        for flag in data['build']['cpuflags']:
            if flag not in request.POST['cpuflags'].split():
                tests = tests.exclude(engine=engine)

    # Skip tests with unmet Syzygy requirments
    if request.POST['syzygy_wdl'] == 'False':
        tests = tests.exclude(syzygy_adj='REQUIRED')
        tests = tests.exclude(syzygy_wdl='REQUIRED')

    # Skip tests that would waste available Threads or exceed them
    options = [x for x in tests if test_maps_onto_thread_count(machine, x)]

    # Finally refine for tests of the highest priority
    if not options: return []
    highest_prio = max(options, key=lambda x: x.priority).priority
    return [test for test in options if test.priority == highest_prio]

def test_maps_onto_thread_count(machine, test):

    # Only assign a workload to a machine if the machine actually has
    # enough Threads for the test. Furthermore, ensure that there are
    # no left over threads when assigned. An exception is made for the
    # case where thread counts differ -- a bad idea to run in general

    dev_threads  = int(extractOption(test.devoptions,  'Threads'))
    base_threads = int(extractOption(test.baseoptions, 'Threads'))

    if max(dev_threads, base_threads) > machine.threads: return False
    return dev_threads != base_threads or machine.threads % dev_threads == 0

def select_workload(machine, tests, variance=0.25):

    # Determine how many threads are assigned to each workload
    table = { test : 0 for test in tests }
    for m in getRecentMachines():
        if m.workload in tests and m != machine:
            table[m.workload] = table[m.workload] + m.threads

    # Find the tests most deserving of resources currently
    ratios = [table[test] / test.throughput for test in tests]
    lowest_idxs = [i for i, r in enumerate(ratios) if r == min(ratios)]

    # Machine is out of date; or there is an unassigned test
    if machine.workload not in tests or min(ratios) == 0:
        return tests[random.choice(lowest_idxs)]

    # No test has less than (1-variance)% of its deserved resources, and
    # therefore we may have this machine repeat its existing workload again
    ideal_ratio = sum(table.values()) / sum([x.throughput for x in tests])
    if min(ratios) / ideal_ratio > 1 - variance:
        return machine.workload

    # Fallback to simply doing the least attention given test
    return tests[random.choice(lowest_idxs)]

def workload_to_dictionary(test, result, machine):

    # Convert the workload into a Dictionary to be used by the Client.
    # The Client must know his Machine ID, his Result ID, and his Test
    # ID. Also, all information about the Test and the associated engines

    return json.dumps({

        'machine' : { 'id'  : machine.id },

        'result'  : { 'id'  : result.id },

        'test'    : {

            'throughput'  : 1000, # HACK: Updated Client's no longer need this value

            'id'          : test.id,
            'engine'      : test.engine,
            'timecontrol' : test.timecontrol,
            'syzygy_adj'  : test.syzygy_adj,
            'syzygy_wdl'  : test.syzygy_wdl,

            'nps'         : OPENBENCH_CONFIG['engines'][test.engine]['nps'],
            'build'       : OPENBENCH_CONFIG['engines'][test.engine]['build'],
            'book'        : OPENBENCH_CONFIG['books'][test.bookname],

            'dev'  : {
                'id'      : test.dev.id,      'name'    : test.dev.name,
                'source'  : test.dev.source,  'sha'     : test.dev.sha,
                'bench'   : test.dev.bench,   'options' : test.devoptions,
                'network' : test.devnetwork,
            },

            'base' : {
                'id'      : test.base.id,     'name'    : test.base.name,
                'source'  : test.base.source, 'sha'     : test.base.sha,
                'bench'   : test.base.bench,  'options' : test.baseoptions,
                'network' : test.basenetwork,
            },
        },
    })


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

    # Tally up the updated WLD stats
    swins   = test.wins   + wins
    slosses = test.losses + losses
    sdraws  = test.draws  + draws
    sgames  = swins + slosses + sdraws

    if test.test_mode == 'SPRT':

        # Compute a new LLR for the updated results
        WLD     = (swins, slosses, sdraws)
        sprt    = OpenBench.stats.SPRT(*WLD, test.elolower, test.eloupper)

        # Check for H0 or H1 being accepted
        passed   = sprt > test.upperllr
        failed   = sprt < test.lowerllr
        finished = passed or failed

    if test.test_mode == 'GAMES':

        # Finish test once we've played the proper amount of games
        passed   = sgames >= test.max_games and swins >= slosses
        failed   = sgames >= test.max_games and swins <  slosses
        finished = passed or failed
        sprt     = 0.0 # Hack to "update" the currentllr

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
