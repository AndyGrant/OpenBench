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

import datetime
import hashlib
import json
import math
import os
import random
import re
import requests

from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.db.models import F
from django.http import FileResponse
from django.utils import timezone
from wsgiref.util import FileWrapper

from OpenSite.settings import MEDIA_ROOT

from OpenBench.config import OPENBENCH_CONFIG
from OpenBench.models import *
from OpenBench.stats import SPRT

import OpenBench.views


class TimeControl(object):

    FIXED_NODES = 'FIXED-NODES' # N= or nodes=
    FIXED_DEPTH = 'FIXED-DEPTH' # D= or depth=
    FIXED_TIME  = 'FIXED-TIME'  # MT= or movetime=
    CYCLIC      = 'CYCLIC'      # X/Y or X/Y+Z
    FISCHER     = 'FISCHER'     # Y or Y+Z

    @staticmethod
    def parse(time_str):

        # Display Nodes as N=, Depth as D=, MoveTime as MT=
        conversion = {
            'N'  :  'N', 'nodes'    :  'N',
            'D'  :  'D', 'depth'    :  'D',
            'MT' : 'MT', 'movetime' : 'MT',
        }

        # Searching for "nodes=", "depth=", and "movetime=" time controls
        pattern = '(?P<mode>((N)|(D)|(MT)|(nodes)|(depth)|(movetime)))=(?P<value>(\d+))'
        if results := re.search(pattern, time_str.upper()):
            mode, value = results.group('mode', 'value')
            return '%s=%s' % (conversion[mode], value)

        # Searching for "X/Y+Z" time controls, where "X/" is optional
        pattern = '(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
        if results := re.search(pattern, time_str):
            moves, base, inc = results.group('moves', 'base', 'inc')

            # Strip the trailing and leading symbols
            moves = None if moves == '' else moves.rstrip('/')
            inc   = 0.0  if inc   is None else inc.lstrip('+')

            # Format the time control for cutechess cleanly
            if moves is None: return '%.1f+%.2f' % (float(base), float(inc))
            return '%d/%.1f+%.2f' % (int(moves), float(base), float(inc))

        print ('FAIL')
        import sys
        sys.stdout.flush()

        raise Exception('Unable to parse Time Control (%s)' % (time_str))

    @staticmethod
    def control_type(time_str):

        # Return one of the types defined at the top of TimeControl

        if time_str.startswith('N='):
            return TimeControl.FIXED_NODES

        if time_str.startswith('D='):
            return TimeControl.FIXED_DEPTH

        if time_str.startswith('MT='):
            return TimeControl.FIXED_TIME

        if '/' in time_str:
            return TimeControl.CYCLIC

        return TimeControl.FISCHER

    @staticmethod
    def control_base(time_str):

        # Fixed-nodes, Fixed-depth, Fixed-time
        if '=' in time_str:
            return int(time_str.split('=')[1])

        # Cyclic
        if '/' in time_str:
            return float(time_str.split('/')[0])

        # Fischer or Sudden Death otherwise
        return float(time_str.split('+')[0])


def path_join(*args):
    return "/".join([f.lstrip("/").rstrip("/") for f in args]).rstrip('/')

def extract_option(options, option):

    match = re.search('(?<={0}=")[^"]*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=\')[^\']*'.format(option), options)
    if match: return match.group()

    match = re.search('(?<={0}=)[^ ]*'.format(option), options)
    if match: return match.group()


def get_pending_tests():
    t = Test.objects.filter(approved=False)
    t = t.exclude(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-creation')

def get_active_tests():
    t = Test.objects.filter(approved=True)
    t = t.exclude(awaiting=True)
    t = t.exclude(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-priority', '-currentllr')

def get_completed_tests():
    t = Test.objects.filter(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-updated')

def get_awaiting_tests():
    t = Test.objects.filter(awaiting=True)
    t = t.exclude(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-creation')


def getRecentMachines(minutes=5):
    target = datetime.datetime.utcnow()
    target = target.replace(tzinfo=timezone.utc)
    target = target - datetime.timedelta(minutes=minutes)
    return Machine.objects.filter(updated__gte=target)

def getMachineStatus(username=None):

    machines = getRecentMachines()

    if username != None:
        machines = machines.filter(user__username=username)

    return ": {0} Machines / ".format(len(machines)) + \
           "{0} Threads / ".format(sum([f.info['concurrency'] for f in machines])) + \
           "{0} MNPS ".format(round(sum([f.info['concurrency'] * f.mnps for f in machines]), 2))

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



def branch_is_out_of_date(test):

    # Cannot compare across engines
    if test.dev_engine != test.base_engine:
        return False

    # Format the request to the Github endpoint
    base = 'https://api.github.com/repos/'
    base = test.dev_repo.replace('github.com', 'api.github.com/repos')
    url  = path_join(base, 'compare', '%s...%s' % (test.dev.sha, test.base.sha))

    try:
        # Out of date if ahead_by is non-zero
        headers = read_git_credentials(test.dev_engine)
        data    = requests.get(url, headers=headers).json()
        return data.get('ahead_by', 0) > 0

    except:
        # If something went wrong, just ignore it
        import traceback
        traceback.print_exc()
        return False

def read_git_credentials(engine):
    fname = 'credentials.%s' % (engine.replace(' ', '').lower())
    if os.path.exists(fname):
        with open(fname) as fin:
            return { 'Authorization' : 'token %s' % fin.readlines()[0].rstrip() }

def requests_illegal_fork(request, field):

    # Strip trailing '/'s for sanity
    engine  = OPENBENCH_CONFIG['engines'][request.POST['%s_engine' % (field)]]
    eng_src = engine['source'].rstrip('/')
    tar_src = request.POST['%s_repo' % (field)].rstrip('/')

    # Illegal if sources do not match for Private engines
    return engine['private'] and eng_src != tar_src

def determine_bench(request, field, message):

    # Use the provided bench if possible
    try: return int(request.POST['{0}_bench'.format(field)])
    except: pass

    # Fallback to try to parse the Bench from the commit
    try:
        benches = re.findall('(?:BENCH|NODES)[ :=]+([0-9,]+)', message, re.IGNORECASE)
        return int(benches[-1].replace(',', ''))
    except: return None

def collect_github_info(request, errors, field):

    # Get branch name / commit sha / tag, and the API path for it
    branch = request.POST['{0}_branch'.format(field)]
    bysha  = bool(re.search('[0-9a-fA-F]{40}', branch))

    # All API requests will share this common path. Some engines are private.
    base    = request.POST['%s_repo' % (field)].replace('github.com', 'api.github.com/repos')
    engine  = request.POST['%s_engine' % (field)]
    private = OPENBENCH_CONFIG['engines'][engine]['private']
    headers = {}

    ## Step 1: Verify the target of the API requests
    ## [A] We will not attempt to reach any site other than api.github.com
    ## [B] Private engines may only use their main repo for sources of tests
    ## [C] Determine which, if any, credentials we want to pass along

    # Private engines must have a token stored in credentials.enginename
    if private and not (headers := read_git_credentials(engine)):
        errors.append('Server does not have access tokens for this engine')
        return (None, None)

    # Do not allow private engines to use forked repos ( We don't have a token! )
    if requests_illegal_fork(request, field):
        errors.append('Forked Repositories are not allowed for Private engines')
        return (None, None)

    # Avoid leaking our credentials to other websites
    if not base.startswith('https://api.github.com/'):
        errors.append('OpenBench may only reach Github\'s API')
        return (None, None)

    ## Step 2: Connect to the Github API for the given Branch or Commit SHA.
    ## [A] We will attempt to parse the most recent commit message for a
    ##     bench, unless one was supplied.
    ## [B] We will translate any branch name into a commit SHA for later use,
    ##     so we may compare branches and generate diff URLs
    ## [C] If the engine is public, we will construct the URL to download the
    ##     source code from Github into a .zip file.
    ## [D] If the engine is private, we will carry onto Step 3.

    try: # Fetch data from the Github API

        # Lookup branch or commit sha, but will fail for tags
        url  = path_join(base, 'commits' if bysha else 'branches', branch)
        data = requests.get(url, headers=headers).json()

        # Check to see if the branch name was actually a tag name
        if not bysha and 'commit' not in data:
            url  = path_join(base, 'commits', branch)
            data = requests.get(url, headers=headers).json()

        # Actual branches have to go one layer deeper
        elif not bysha: data = data['commit']

        # Check that all the data we need going forward is present
        assert 'message' in data['commit'] and 'sha' in data
        assert private or 'sha' in data['commit']['tree']

    except: # Unable to find for whatever reason
        import traceback
        traceback.print_exc()
        errors.append('%s could not be found' % (branch))
        return (None, None)

    # Extract the bench from the web form, or from the commit message
    if not (bench := determine_bench(request, field, data['commit']['message'])):
        errors.append('Unable to parse a Bench for %s' % (branch))
        return (None, None)

    # Public Engines: Construct the .zip download and return everything
    if not private:
        treeurl = data['commit']['tree']['sha'] + '.zip'
        source  = path_join(request.POST['%s_repo' % (field)], 'archive', treeurl)
        return (source, branch, data['sha'], bench), True

    ## Step 3: Construct the URL for the API request to list all Artifacts
    ## [A] OpenBench artifacts are always run via a file named openbench.yml
    ## [B] These should contain combinations for windows/linux, avx2/avx512, popcnt/pext
    ## [C] If those artifacts are not found, we flag the test as awaiting, and try later.

    url, has_all = fetch_artifact_url(base, engine, headers, data['sha'])
    return (url, branch, data['sha'], bench), has_all

def fetch_artifact_url(base, engine, headers, sha):

    try:
        # Fetch the run id for the openbench workflow for this comment
        url    = path_join(base, 'actions', 'workflows', 'openbench.yml', 'runs')
        url   += '?head_sha=%s' % (sha)
        run_id = requests.get(url=url, headers=headers).json()['workflow_runs'][0]['id']

        # Fetch information about individual job results
        url  = path_join(base, 'actions', 'runs', str(run_id), 'jobs')
        jobs = requests.get(url=url, headers=headers).json()['jobs']

        # Fetch information about individual artifact
        url       = path_join(base, 'actions', 'runs', str(run_id), 'artifacts')
        artifacts = requests.get(url=url, headers=headers).json()['artifacts']

        # All jobs finished, with at least one non-expired Artifact
        assert not any(job['conclusion'] != 'success' for job in jobs)
        assert not any(artifact['expired'] for artifact in artifacts)
        assert len(artifacts) >= len(jobs)

        # Only set the url if we have everything we need
        return (url, True)

    except Exception as error:
        # If anything goes wrong, retry later with the same base URL
        return (base, False)

def verify_test_creation(request):

    errors = []

    def verify_integer(field, field_name):
        try: int(request.POST[field])
        except: errors.append('"{0}" is not an Integer'.format(field_name))

    def verify_greater_than(field, field_name, value):
        try: assert int(request.POST[field]) > value
        except: errors.append('"{0}" is not greater than {1}'.format(field_name, value))

    def verify_options(field, option, field_name):
        try: assert int(extract_option(request.POST[field], option)) >= 1
        except: errors.append('"{0}" needs to be at least 1 for {1}'.format(option, field_name))

    def verify_configuration(field, field_name, parent):
        try: assert request.POST[field] in OPENBENCH_CONFIG[parent].keys()
        except: errors.append('{0} was not found in the configuration'.format(field_name))

    def verify_time_control(field, field_name):
        try: TimeControl.parse(request.POST[field])
        except: errors.append('{0} is not parsable'.format(field_name))

    def verify_win_adj(field):
        try:
            if (content := request.POST[field]) == 'None': return
            assert re.match('movecount=[0-9]+ score=[0-9]+', content)
        except: errors.append('Invalid Win Adjudication Setting. Try "None"?')

    def verify_draw_adj(field):
        try:
            if (content := request.POST[field]) == 'None': return
            assert re.match('movenumber=[0-9]+ movecount=[0-9]+ score=[0-9]+', content)
        except: errors.append('Invalid Draw Adjudication Setting. Try "None"?')

    def verify_github_repo(field):
        pattern = r'^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+\/?$'
        try: assert re.match(pattern, request.POST[field])
        except: errors.append('Sources must be found on https://github.com/<User>/<Repo>')

    def verify_network(field, field_name, engine_field):
        try:
            if request.POST[field] == '': return
            Network.objects.get(engine=request.POST[engine_field], sha256=request.POST[field])
        except: errors.append('Unknown Network Provided for {0}'.format(field_name))

    def verify_test_mode(field):
        try: assert request.POST[field] in ['SPRT', 'GAMES']
        except: errors.append('Unknown Test Mode')

    def verify_sprt_bounds(field):
        try:
            if request.POST['test_mode'] != 'SPRT': return
            pattern = r'^\[(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\]$'
            match   = re.match(pattern, request.POST['test_bounds'])
            assert float(match.group(1)) < float(match.group(2))
        except: errors.append('SPRT Bounds must be formatted as [float1, float2]')

    def verify_sprt_conf(field):
        try:
            if request.POST['test_mode'] != 'SPRT': return
            pattern = r'^\[(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\]$'
            match   = re.match(pattern, request.POST['test_confidence'])
            assert 0.00 < float(match.group(1)) < 1.00
            assert 0.00 < float(match.group(2)) < 1.00
        except: errors.append('Confidence Bounds must be formatted as [float1, float2], within (0.00, 1.00)')

    def verify_max_games(field):
        try:
            if request.POST['test_mode'] != 'GAMES': return
            assert int(request.POST['test_max_games']) > 0
        except: errors.append('Fixed Games Tests must last at least one game')

    def verify_syzygy_field(field, field_name):
        candidates = ['OPTIONAL', 'DISABLED', '3-MAN', '4-MAN', '5-MAN', '6-MAN', '7-MAN']
        try: assert request.POST[field] in candidates
        except: errors.append('%s must be in %s' % (field_name, ', '.join(candidates)))

    verifications = [

        # Verify everything about the Dev Engine
        (verify_configuration, 'dev_engine', 'Dev Engine', 'engines'),
        (verify_github_repo  , 'dev_repo'),
        (verify_network      , 'dev_network', 'Dev Network', 'dev_engine'),
        (verify_options      , 'dev_options', 'Threads', 'Dev Options'),
        (verify_options      , 'dev_options', 'Hash', 'Dev Options'),
        (verify_time_control , 'dev_time_control', 'Dev Time Control'),

        # Verify everything about the Base Engine
        (verify_configuration, 'base_engine', 'Base Engine', 'engines'),
        (verify_github_repo  , 'base_repo'),
        (verify_network      , 'base_network', 'Base Network', 'base_engine'),
        (verify_options      , 'base_options', 'Threads', 'Base Options'),
        (verify_options      , 'base_options', 'Hash', 'Base Options'),
        (verify_time_control , 'base_time_control', 'Base Time Control'),

        # Verify everything about the Test Settings
        (verify_configuration, 'book_name', 'Book', 'books'),
        (verify_test_mode    , 'test_mode'),
        (verify_sprt_bounds  , 'test_bounds'),
        (verify_sprt_conf    , 'test_confidence'),
        (verify_max_games    , 'test_max_games'),

        # Verify everything about the General Settings
        (verify_integer      , 'priority', 'Priority'),
        (verify_greater_than , 'throughput', 'Throughput', 0),
        (verify_syzygy_field , 'syzygy_wdl', 'Syzygy WDL'),

        # Verify everything about the Workload Settings
        (verify_greater_than , 'report_rate', 'Report Rate', 0),
        (verify_greater_than , 'workload_size', 'Workload Size', 0),

        # Verify everything about the Adjudicaton Settings
        (verify_syzygy_field , 'syzygy_adj', 'Syzygy Adjudication'),
        (verify_win_adj      , 'win_adj'),
        (verify_draw_adj     , 'draw_adj'),
    ]

    for verification in verifications:
        verification[0](*verification[1:])

    return errors

def create_new_test(request):

    # Verify all of the fields in the request
    if (errors := verify_test_creation(request)):
        return None, errors

    # Collect Github meta information (Shas, Sources, Benches)
    devinfo,  dev_has_all  = collect_github_info(request, errors, 'dev')
    baseinfo, base_has_all = collect_github_info(request, errors, 'base')
    if errors != []: return None, errors

    test                   = Test()
    test.author            = request.user.username
    test.book_name         = request.POST['book_name']

    test.dev               = getEngine(*devinfo)
    test.dev_repo          = request.POST['dev_repo']
    test.dev_engine        = request.POST['dev_engine']
    test.dev_options       = request.POST['dev_options']
    test.dev_network       = request.POST['dev_network']
    test.dev_time_control  = TimeControl.parse(request.POST['dev_time_control'])

    test.base              = getEngine(*baseinfo)
    test.base_repo         = request.POST['base_repo']
    test.base_engine       = request.POST['base_engine']
    test.base_options      = request.POST['base_options']
    test.base_network      = request.POST['base_network']
    test.base_time_control = TimeControl.parse(request.POST['base_time_control'])

    test.report_rate       = int(request.POST['report_rate'])
    test.workload_size     = int(request.POST['workload_size'])
    test.priority          = int(request.POST['priority'])
    test.throughput        = int(request.POST['throughput'])

    test.syzygy_wdl        = request.POST['syzygy_wdl']
    test.syzygy_adj        = request.POST['syzygy_adj']
    test.win_adj           = request.POST['win_adj']
    test.draw_adj          = request.POST['draw_adj']

    test.test_mode         = request.POST['test_mode']
    test.awaiting          = not (dev_has_all and base_has_all)

    if test.test_mode == 'SPRT':
        test.elolower = float(request.POST['test_bounds'].split(',')[0].lstrip('['))
        test.eloupper = float(request.POST['test_bounds'].split(',')[1].rstrip(']'))
        test.alpha    = float(request.POST['test_confidence'].split(',')[1].rstrip(']'))
        test.beta     = float(request.POST['test_confidence'].split(',')[0].lstrip('['))
        test.lowerllr = math.log(test.beta / (1.0 - test.alpha))
        test.upperllr = math.log((1.0 - test.beta) / test.alpha)

    if test.test_mode == 'GAMES':
        test.max_games = int(request.POST['test_max_games'])

    if test.dev_network:
        test.dev_netname = Network.objects.get(engine=test.dev_engine, sha256=test.dev_network).name

    if test.base_network:
        test.base_netname = Network.objects.get(engine=test.base_engine, sha256=test.base_network).name

    test.save()

    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    return test, None


def get_machine(machineid, user, info):

    # Create a new machine if we don't have an id
    if machineid == 'None':
        return Machine(user=user, info=info)

    # Fetch the requested machine, which hopefully exists
    try: machine = Machine.objects.get(id=int(machineid))
    except: return None

    # Workload requests should always contain a MAC
    if 'mac_address' not in machine.info:
        return None

    # Soft-verify by checking if the MAC addresses match
    if machine.info['mac_address'] != info['mac_address']:
        return None

    return machine

def get_workload(machine):

    # Check to make sure we have a potential workload
    if not (tests := get_valid_workloads(machine)):
        return {}

    # Select from valid workloads the most needing test
    test = select_workload(machine, tests)

    try: result = Result.objects.get(test=test, machine=machine)
    except: result = Result(test=test, machine=machine)

    # Update the Machine's status and save everything
    machine.workload = test.id; machine.save(); result.save()
    return { 'workload' : workload_to_dictionary(test, result) }


# Purely Helper functions for Networks views

def network_disambiguate(engine, identifier):

    candidates = Network.objects.filter(engine=engine)

    # Identifier actually refers to the Network name
    if (network := candidates.filter(name=identifier).first()):
        return network

    # Identifier actually refers to the Network SHA
    if (network := candidates.filter(sha256=identifier).first()):
        return network

    # No Network exists with engine this Name or Sha
    return None

def network_upload(request, engine, name):

    # Extract and process the Network file to produce a SHA
    netfile = request.FILES['netfile']
    sha256  = hashlib.sha256(netfile.file.read()).hexdigest()[:8].upper()

    # Rejecct Networks with strange characters
    if not re.match(r'^[a-zA-Z0-9_.-]+$', name):
        return OpenBench.views.redirect(request, '/networks/', error='Valid characters are [a-zA-Z0-9_.-]')

    # Don't allow duplicate uploads for the same engine
    if Network.objects.filter(engine=engine, sha256=sha256):
        return OpenBench.views.redirect(request, '/networks/', error='Network with that hash already exists for that engine')

    # Don't allow duplicate uploads for the same engine
    if Network.objects.filter(engine=engine, name=name):
        return OpenBench.views.redirect(request, '/networks/', error='Network with that name already exists for that engine')

    # Filter out anyone who has used an unknown engine
    if engine not in OPENBENCH_CONFIG['engines'].keys():
        return OpenBench.views.redirect(request, '/networks/', error='No Engine found with matching name')

    # Save the file locally into /Media/ if we don't already have this file
    if not Network.objects.filter(sha256=sha256):
        FileSystemStorage().save('%s' % (sha256), netfile)

    # Create the Network object mapping to the saved local file
    Network.objects.create(
        sha256=sha256, name=name,
        engine=engine, author=request.user.username)

    # Redirect to Engine specific view, to add clarity
    return OpenBench.views.redirect(request, '/networks/%s/' % (engine), status='Uploaded %s for %s' % (name, engine))

def network_default(request, engine, network):

    # Update default to False for all Networks, except this one
    Network.objects.filter(engine=engine).update(default=False)
    network.default = True; network.save()

    # Report this, and refer to the Engine specific view
    status = 'Set %s as default for %s' % (network.name, network.engine)
    return OpenBench.views.redirect(request, '/networks/%s/' % (network.engine), status=status)

def network_delete(request, engine, network):

    # Save information before deleting the Network Model
    status = 'Deleted %s for %s' % (network.name, network.engine)
    sha256 = network.sha256; network.delete()

    # Only delete the actual file if no other engines use it
    if not Network.objects.filter(sha256=sha256):
        FileSystemStorage().delete(sha256)

    # Report this, and refer to the Engine specific view
    return OpenBench.views.redirect(request, '/networks/%s/' % (engine), status=status)

def network_download(request, engine, network):

    # Craft the download HTML response
    netfile  = os.path.join(MEDIA_ROOT, network.sha256)
    fwrapper = FileWrapper(open(netfile, 'rb'), 8192)
    response = FileResponse(fwrapper, content_type='application/octet-stream')

    # Set all headers and return response
    response['Expires'] = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).ctime()
    response['Content-Length'] = os.path.getsize(netfile)
    response['Content-Disposition'] = 'attachment; filename=' + network.sha256
    return response


# Purely Helper functions for get_workload()

def get_valid_workloads(machine):

    # Skip anything that is not running
    tests = get_active_tests()

    # Skip engines that the Machine cannot handle
    for engine in OPENBENCH_CONFIG['engines'].keys():
        if engine not in machine.info['supported']:
            tests = tests.exclude(dev_engine=engine)
            tests = tests.exclude(base_engine=engine)

    # Skip tests with unmet Syzygy requirments
    for K in range(machine.info['syzygy_max'] + 1, 10):
        tests = tests.exclude(syzygy_adj='%d-MAN' % (K))
        tests = tests.exclude(syzygy_wdl='%d-MAN' % (K))

    # Skip tests that would waste available Threads or exceed them
    threads      = machine.info['concurrency']
    sockets      = machine.info['sockets']
    hyperthreads = machine.info['physical_cores'] < threads
    options = [x for x in tests if
        test_maps_onto_thread_count(x, threads, sockets, hyperthreads)]

    # Finally refine for tests of the highest priority
    if not options: return []
    highest_prio = max(options, key=lambda x: x.priority).priority
    return [test for test in options if test.priority == highest_prio]

def test_maps_onto_thread_count(test, threads, sockets, hyperthreads):

    dev_threads  = int(extract_option(test.dev_options,  'Threads'))
    base_threads = int(extract_option(test.base_options, 'Threads'))

    # Each individual cutechess copy must have access to sufficient Threads
    if max(dev_threads, base_threads) > (threads / sockets):
        return False

    # Refuse to run thread-odds when dipping into hyperthreads
    return dev_threads == base_threads or not hyperthreads

def select_workload(machine, tests, variance=0.25):

    # Determine how many threads are assigned to each workload
    table = { test.id : { 'cores' : 0, 'throughput' : test.throughput } for test in tests }
    for m in getRecentMachines():
        if m.workload in table and m != machine:
            table[m.workload]['cores'] += m.info['concurrency']

    # Find the tests most deserving of resources currently
    ratios = [table[x]['cores'] / table[x]['throughput'] for x in table]
    lowest_idxs = [i for i, r in enumerate(ratios) if r == min(ratios)]

    # Machine is out of date; or there is an unassigned test
    if machine.workload not in table or min(ratios) == 0:
        return tests[random.choice(lowest_idxs)]

    # No test has less than (1-variance)% of its deserved resources, and
    # therefore we may have this machine repeat its existing workload again
    ideal_ratio = sum([x['cores'] for x in table.values()]) / sum([x['throughput'] for x in table.values()])
    if min(ratios) / ideal_ratio > 1 - variance:
        return Test.objects.get(id=machine.workload)

    # Fallback to simply doing the least attention given test
    return tests[random.choice(lowest_idxs)]

def workload_to_dictionary(test, result):

    return {

        'result' : {
            'id'  : result.id
        },

        'test' : {
            'id'            : test.id,
            'syzygy_wdl'    : test.syzygy_wdl,
            'syzygy_adj'    : test.syzygy_adj,
            'win_adj'       : test.win_adj,
            'draw_adj'      : test.draw_adj,
            'report_rate'   : test.report_rate,
            'workload_size' : test.workload_size,
            'book'          : OPENBENCH_CONFIG['books'][test.book_name],

            'dev' : {
                'id'           : test.dev.id,
                'name'         : test.dev.name,
                'source'       : test.dev.source,
                'sha'          : test.dev.sha,
                'bench'        : test.dev.bench,
                'engine'       : test.dev_engine,
                'options'      : test.dev_options,
                'network'      : test.dev_network,
                'time_control' : test.dev_time_control,
                'nps'          : OPENBENCH_CONFIG['engines'][test.dev_engine]['nps'],
                'build'        : OPENBENCH_CONFIG['engines'][test.dev_engine]['build'],
                'private'      : OPENBENCH_CONFIG['engines'][test.dev_engine]['private'],
            },

           'base' : {
                'id'           : test.base.id,
                'name'         : test.base.name,
                'source'       : test.base.source,
                'sha'          : test.base.sha,
                'bench'        : test.base.bench,
                'engine'       : test.base_engine,
                'options'      : test.base_options,
                'network'      : test.base_network,
                'time_control' : test.base_time_control,
                'nps'          : OPENBENCH_CONFIG['engines'][test.base_engine]['nps'],
                'build'        : OPENBENCH_CONFIG['engines'][test.base_engine]['build'],
                'private'      : OPENBENCH_CONFIG['engines'][test.base_engine]['private'],
            },
        },
    }


def update_test(request, machine):

    # Extract error information
    crashes    = int(request.POST['crashes'   ])
    timelosses = int(request.POST['timelosses'])
    illegals   = int(request.POST['illegals'  ])
    has_error  = crashes or timelosses or illegals

    # Extract Database information
    machine_id = int(request.POST['machine_id'])
    result_id  = int(request.POST['result_id' ])
    test_id    = int(request.POST['test_id'   ])

    # Trinomial Implementation
    losses, draws, wins = map(int, request.POST['trinomial'].split())
    games = losses + draws + wins

    # Pentanomial Implementation
    # ll, dl, dd, dw, ww = map(int, request.POST['pentanomial'].split())
    # games = ll + dl + dd + dw + ww

    with transaction.atomic():

        test = Test.objects.get(id=test_id)
        if test.finished or test.deleted:
            return { 'stop' : True }

        test.losses += losses
        test.draws  += draws
        test.wins   += wins
        test.games  += games

        test.error = test.error or has_error

        if test.test_mode == 'SPRT':

            # Compute a new LLR for the updated results
            WLD = (test.wins, test.losses, test.draws)
            test.currentllr = SPRT(*WLD, test.elolower, test.eloupper)

            # Check for H0 or H1 being accepted
            test.passed   = test.currentllr > test.upperllr
            test.failed   = test.currentllr < test.lowerllr
            test.finished = test.passed or test.failed

        elif test.test_mode == 'GAMES':

            # Finish test once we've played the proper amount of games
            test.passed   = test.games >= test.max_games and test.wins >= test.losses
            test.failed   = test.games >= test.max_games and test.wins <  test.losses
            test.finished = test.passed or test.failed

        test.save()

    # Update Result object; No risk from concurrent access
    Result.objects.filter(id=result_id).update(
        games   = F('games')   + games,   wins     = F('wins'    ) + wins,
        losses  = F('losses')  + losses,  draws    = F('draws'   ) + draws,
        crashes = F('crashes') + crashes, timeloss = F('timeloss') + timelosses,
        updated=timezone.now()
    )

    # Update Profile object; No risk from concurrent access
    Profile.objects.filter(user=Machine.objects.get(id=machine_id).user).update(
        games=F('games') + games,
        updated=timezone.now()
    )

    # Update Machine object; No risk from concurrent access
    Machine.objects.filter(id=machine_id).update(
        updated=timezone.now()
    )

    return [{}, { 'stop' : True }][test.finished]
