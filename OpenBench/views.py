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

import os, hashlib, datetime, json, secrets, sys, re

import django.http
import django.shortcuts
import django.contrib.auth

import OpenBench.config
import OpenBench.utils

from OpenBench.config import OPENBENCH_CONFIG

from OpenBench.models import *
from django.contrib.auth.models import User
from OpenSite.settings import MEDIA_ROOT

from django.db.models import F, Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                              GENERAL UTILITIES                              #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

class UnableToAuthenticate(Exception):
    pass

def render(request, template, content={}, always_allow=False, error=None, warning=None, status=None):

    data = content.copy()
    data.update({ 'config' : OPENBENCH_CONFIG })

    if OpenBench.config.REQUIRE_LOGIN_TO_VIEW:
        if not request.user.is_authenticated and not always_allow:
            return redirect(request, '/login/',  error=data['config']['error']['requires_login'])

    if request.user.is_authenticated:

        profile = Profile.objects.filter(user=request.user)
        data.update({'profile' : profile.first()})

        if profile.first() and not profile.first().enabled:
            request.session['error_message'] = data['config']['error']['disabled']

        elif request.user.is_authenticated and not profile.first():
            request.session['error_message'] = data['config']['error']['fakeuser']

    if error:
        request.session['error_message'] = error

    if warning:
        request.session['warning_message'] = error

    if status:
        request.session['status_message'] = status

    response = django.shortcuts.render(request, 'OpenBench/{0}'.format(template), data)

    for key in ['status_message', 'warning_message', 'error_message']:
        if key in request.session: del request.session[key]

    return response

def redirect(request, destination, error=None, warning=None, status=None):

    if error:
        request.session['error_message'] = error

    if warning:
        request.session['warning_message'] = warning

    if status:
        request.session['status_message'] = status

    return django.http.HttpResponseRedirect(destination)

def authenticate(request, requireEnabled=False):

    try:
        user = django.contrib.auth.authenticate(
            username = request.POST['username'],
            password = request.POST['password'])

        if requireEnabled:
            profile = OpenBench.models.Profile.objects.get(user=user)
            if not profile.enabled: raise UnableToAuthenticate()

    except Exception:
        raise UnableToAuthenticate()

    if user is None:
        raise UnableToAuthenticate()

    return user

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                            ADMINISTRATIVE VIEWS                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def register(request):

    if request.method == 'GET':
        if not OpenBench.config.REQUIRE_MANUAL_REGISTRATION:
            return render(request, 'register.html', always_allow=True)
        return redirect(request, '/login/', error=OPENBENCH_CONFIG['error']['manual_registration'])

    if request.POST['password1'] != request.POST['password2']:
        return redirect(request, '/register/', error='Passwords do not match')

    if not request.POST['username'].isalnum():
        return redirect(request, '/register/', error='Alpha-numeric usernames Only')

    if User.objects.filter(username=request.POST['username']):
        return redirect(request, '/register/', error='That username is already taken')

    email    = request.POST['email']
    username = request.POST['username']
    password = request.POST['password1']

    user = User.objects.create_user(username, email, password)
    django.contrib.auth.login(request, user)
    Profile.objects.create(user=user)

    return redirect(request, '/index/')

def login(request):

    if request.method == 'GET':
        return render(request, 'login.html', always_allow=True)

    try:
        django.contrib.auth.login(request, authenticate(request))
        return redirect(request, '/index/')

    except UnableToAuthenticate:
        return redirect(request, '/login/', error='Unable to authenticate user')

def logout(request):

    django.contrib.auth.logout(request)
    return redirect(request, '/index/', status='Logged out')

def profile(request):

    if not request.user.is_authenticated:
        return redirect(request, '/login/')

    if not Profile.objects.filter(user=request.user).first():
        return redirect(request, '/index/')

    if request.method == 'GET':
        return render(request, 'profile.html')

    changes_message = ''
    if request.user.email != request.POST['email']:
        changes_message += 'Updated email address to %s' % (request.POST['email'])
        request.user.email = request.POST['email']
        request.user.save()

    if request.POST['password1'] != request.POST['password2']:
        return redirect(request, '/profile/', status=changes_message, error='Passwords do not match')

    if request.POST['password1']:
        request.user.set_password(request.POST['password1'])
        request.user.save()
        django.contrib.auth.login(request, request.user)
        changes_message += '\nUpdated password'

    return redirect(request, '/profile/', status=changes_message.removeprefix('\n'))

def profile_config(request):

    if not request.user.is_authenticated:
        return redirect(request, '/login/')

    if not (profile := Profile.objects.filter(user=request.user).first()):
        return redirect(request, 'index')

    if request.method == 'GET':
        return render(request, 'profile.html')

    changes = ''

    if (engine := request.POST.get('default-status', profile.engine)) != profile.engine:
        changes += 'Set %s as the default, replacing %s\n' % (engine, profile.engine)
        profile.engine = engine

    for engine in json.loads(request.POST.get('deleted-repos', '[]')):
        profile.repos.pop(engine, False)
        changes += 'Deleted Engine: %s\n' % (engine)

    if changes:
        profile.save()

    engine_name = request.POST.get('new-engine-name', 'None')
    engine_repo = request.POST.get('new-engine-repo', '').removesuffix('/')

    if engine_name != 'None' and engine_repo:

        if not engine_repo.startswith('https://github.com/'):
            return redirect(request, '/profile/', error='Repositories must be on Github')

        if not profile.engine:
            profile.engine = engine_name

        changes += 'Added Engine: %s at %s' % (engine_name, engine_repo)
        profile.repos[engine_name] = engine_repo
        profile.save()

    return redirect(request, '/profile/', status=changes)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                               TEST LIST VIEWS                               #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def index(request, page=1):

    pending   = OpenBench.utils.get_pending_tests()
    active    = OpenBench.utils.get_active_tests()
    completed = OpenBench.utils.get_completed_tests()
    awaiting  = OpenBench.utils.get_awaiting_tests()

    start, end, paging = OpenBench.utils.getPaging(completed, page, 'index')

    data = {
        'pending'   : pending,
        'active'    : active,
        'completed' : completed[start:end],
        'awaiting'  : awaiting,
        'paging'    : paging,
        'status'    : OpenBench.utils.getMachineStatus(),
    }

    return render(request, 'index.html', data)

def user(request, username, page=1):

    pending   = OpenBench.utils.get_pending_tests().filter(author=username)
    active    = OpenBench.utils.get_active_tests().filter(author=username)
    completed = OpenBench.utils.get_completed_tests().filter(author=username)
    awaiting  = OpenBench.utils.get_awaiting_tests().filter(author=username)

    start, end, paging = OpenBench.utils.getPaging(completed, page, 'user/%s' % (username))

    data = {
        'pending'   : pending,
        'active'    : active,
        'completed' : completed[start:end],
        'awaiting'  : awaiting,
        'paging'    : paging,
        'status'    : OpenBench.utils.getMachineStatus(username),
    }

    return render(request, 'index.html', data)

def greens(request, page=1):

    completed = OpenBench.utils.get_completed_tests().filter(passed=True)
    start, end, paging = OpenBench.utils.getPaging(completed, page, 'greens')

    data = { 'completed' : completed[start:end], 'paging' : paging }
    return render(request, 'index.html', data)

def search(request):

    if request.method == 'GET':
        return render(request, 'search.html', {})

    tests = Test.objects.all()

    # Optional Selection box filters

    if request.POST['author']:
        tests = tests.filter(author=request.POST['author'])

    if request.POST['engine']:
        tests = tests.filter(Q(base_engine=request.POST['engine']) | Q(dev_engine=request.POST['engine']))

    if request.POST['opening-book']:
        tests = tests.filter(book_name=request.POST['opening-book'])

    if request.POST['test-mode']:
        tests = tests.filter(test_mode=request.POST['test-mode'])

    if request.POST['syzygy-wdl']:
        tests = tests.filter(syzygy_wdl=request.POST['syzygy-wdl'])

    # Checkboxes for Test statuses

    if 'show-greens' not in request.POST:
        tests = tests.annotate(x=F('elolower') + F('eloupper')).exclude(x__gte=0, passed=True)

    if 'show-yellows' not in request.POST:
        tests = tests.exclude(failed=True, wins__gte=F('losses'))

    if 'show-reds' not in request.POST:
        tests = tests.exclude(failed=True, wins__lt=F('losses'))

    if 'show-blues' not in request.POST:
        tests = tests.annotate(x=F('elolower') + F('eloupper')).exclude(x__lt=0, passed=True)

    if 'show-stopped' not in request.POST:
        tests = tests.exclude(passed=False, failed=False)

    if 'show-deleted' not in request.POST:
        tests = tests.exclude(deleted=True)

    # Remaining filtering is hard to do with standard Django queries

    filtered = []
    keywords = request.POST['keywords'].upper().split()

    tc_type   = request.POST['tc-type']
    tc_value  = request.POST['tc-value-input']
    tc_select = request.POST['tc-value-select']

    # Attempt to parse the time control

    try:
        if tc_value:
            tc_value = OpenBench.utils.TimeControl.parse(tc_value)
    except:
        return redirect(request, '/search/', error='Invalid Time Control')

    # Filter out tests

    for test in tests:

        # None of the keywords appear in the dev branch name
        if keywords and not any(x in test.dev.name.upper() for x in keywords):
            continue

        # Determine the max number of threads that either engine used
        dev_threads  = OpenBench.utils.extract_option(test.dev_options, 'Threads')
        base_threads = OpenBench.utils.extract_option(test.base_options, 'Threads')
        max_threads  = max(int(dev_threads), int(base_threads))

        # Extract requsted configuration
        select_value = request.POST['threads-select']
        input_value  = int(request.POST['threads-input'])

        # Requested Threads value did not match observed value
        if select_value == '='  and max_threads != input_value: continue
        if select_value == '>=' and max_threads  < input_value: continue
        if select_value == '<=' and max_threads  > input_value: continue

        # Filter our undesired time control types
        if tc_type and tc_type != OpenBench.utils.TimeControl.control_type(test.dev_time_control):
            continue

        # Filter tests of the same time control type, but outside our range
        if tc_value:

            search_base = OpenBench.utils.TimeControl.control_base(tc_value)
            test_base   = OpenBench.utils.TimeControl.control_base(test.dev_time_control)

            if tc_select == '='  and search_base != test_base: continue
            if tc_select == '>=' and search_base  > test_base: continue
            if tc_select == '<=' and search_base  < test_base: continue

        filtered.append(test)

    error = 'No matching tests found' if not len(filtered) else None
    return render(request, 'search.html', { 'tests' : filtered }, error=error)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                           GENERAL DATA TABLE VIEWS                          #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def users(request):

    data = { 'profiles' : Profile.objects.order_by('-games', '-tests') }
    return render(request, 'users.html', data)

def event(request, id):

    try:
        with open(os.path.join(MEDIA_ROOT, LogEvent.objects.get(id=id).log_file)) as fin:
            return render(request, 'event.html', { 'content' : fin.read() })
    except:
        return redirect(request, '/index/', error='No logs for event exist')

def events_actions(request, page=1):

    events = LogEvent.objects.all().filter(machine_id=0).order_by('-id')
    start, end, paging = OpenBench.utils.getPaging(events, page, 'events')

    data = { 'events' : events[start:end], 'paging' : paging };
    return render(request, 'events.html', data)

def events_errors(request, page=1):

    events = LogEvent.objects.all().exclude(machine_id=0).order_by('-id')
    start, end, paging = OpenBench.utils.getPaging(events, page, 'errors')

    data = { 'events' : events[start:end], 'paging' : paging };
    return render(request, 'errors.html', data)

def machines(request, machineid=None):

    if machineid == None:
        data = { 'machines' : OpenBench.utils.getRecentMachines() }
        return render(request, 'machines.html', data)

    try:
        data = { 'machine' : OpenBench.models.Machine.objects.get(id=machineid) }
        return render(request, 'machine.html', data)

    except:
        return redirect(request, '/machines/', error='Machine does not exist')


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                            TEST MANAGEMENT VIEWS                            #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def test(request, id, action=None):

    if not (test := Test.objects.filter(id=id).first()):
        return django.http.HttpResponseRedirect('/index/')

    if action not in ['APPROVE', 'RESTART', 'STOP', 'DELETE', 'MODIFY']:
        data = { 'test' : test, 'results': Result.objects.filter(test=test) }
        return render(request, 'test.html', data)

    if not request.user.is_authenticated:
        return redirect(request, '/login/', error='Only users may interact with tests')

    profile = Profile.objects.get(user=request.user)
    if not profile.approver and test.author != request.user.username:
        return redirect(request, '/index/', error='You cannot interact with another user\'s test')

    if action == 'APPROVE':
        if test.author == request.user.username and not user.is_superuser:
            return redirect(request, '/index/', error='You cannot approve your own test')

    if action == 'APPROVE': test.approved =  True; test.save()
    if action == 'RESTART': test.finished = False; test.save()
    if action == 'STOP'   : test.finished =  True; test.save()
    if action == 'DELETE' : test.deleted  =  True; test.save()

    if action == 'MODIFY':
        test.priority      = int(request.POST['priority'])
        test.throughput    = max(1, int(request.POST['throughput']))
        test.report_rate   = max(1, int(request.POST['report_rate']))
        test.workload_size = max(1, int(request.POST['workload_size']))
        test.save()

    action += " P=%d TP=%d RR=%d WS=%d" % (test.priority, test.throughput, test.report_rate, test.workload_size)
    LogEvent.objects.create(author=request.user.username, summary=action, log_file='', test_id=test.id)
    return django.http.HttpResponseRedirect('/index/')

def create_test(request):

    if not request.user.is_authenticated:
        return redirect(request, '/login/', error='Only enabled users can create tests')

    if not Profile.objects.get(user=request.user).enabled:
        return redirect(request, '/login/', error='Only enabled users can create tests')

    if request.method == 'GET':
        data = { 'networks' : list(Network.objects.all().values()) }
        return render(request, 'create_test.html', data)

    test, errors = OpenBench.utils.create_new_test(request)
    if errors != [] and errors != None:
        return redirect(request, '/newTest/', error='\n'.join(errors))

    if warning := OpenBench.utils.branch_is_out_of_date(test):
        warning = 'Consider Rebasing: Dev (%s) appears behind Base (%s)' % (test.dev.name, test.base.name)

    username = request.user.username
    profile  = Profile.objects.get(user=request.user)
    LogEvent.objects.create(author=username, summary='CREATE', log_file='', test_id=test.id)

    approved = Test.objects.filter(approved=True)
    A = approved.filter( dev__sha=test.dev.sha).exists()
    B = approved.filter(base__sha=test.dev.sha).exists()
    C = approved.filter( dev__sha=test.base.sha).exists()
    D = approved.filter(base__sha=test.base.sha).exists()

    if (A or B) and (C or D):
        test.approved = True; test.save()
        action = "AUTOAPP P={0} TP={1}".format(test.priority, test.throughput)
        LogEvent.objects.create(author=username, summary=action, log_file='', test_id=test.id)

    elif not OpenBench.config.USE_CROSS_APPROVAL and profile.approver:
        test.approved = True; test.save()
        action = "APPROVE P={0} TP={1}".format(test.priority, test.throughput)
        LogEvent.objects.create(author=username, summary=action, log_file='', test_id=test.id)

    return redirect(request, '/index/', warning=warning)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                          NETWORK MANAGEMENT VIEWS                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def networks(request, engine=None, action=None, name=None, client=False):

    # Without an identifier and a valid action, all we can do is view the list
    if not name or action.upper() not in ['UPLOAD', 'DEFAULT', 'DELETE', 'DOWNLOAD']:
        networks = Network.objects.all()
        if engine and engine in OPENBENCH_CONFIG['engines'].keys():
            networks = networks.filter(engine=engine)
        return render(request, 'networks.html', { 'networks' : list(networks.order_by('-id').values()) })

    # Require logins. Clients will be artifically logged in
    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    # Require approver credentials, unless downloading as a client
    if not client and not Profile.objects.get(user=request.user).approver:
        return django.http.HttpResponseRedirect('/index/')

    # Split out Uploads, since there is no logic to disambiguate the name
    if action.upper() == 'UPLOAD':
        return OpenBench.utils.network_upload(request, engine, name)

    # Push off all the actual effort to OpenBench.utils for all actions
    actions = {
        'DEFAULT'  : OpenBench.utils.network_default,
        'DELETE'   : OpenBench.utils.network_delete,
        'DOWNLOAD' : OpenBench.utils.network_download,
    }

    # Update the Network, if we can find one for the given name/sha256
    if (network := OpenBench.utils.network_disambiguate(engine, name)):
        return actions[action.upper()](request, engine, network)

    # Otherwise we could not find the Network, and cannot do anything
    return redirect(request, '/networks/', error='No network found with matching Sha')

def network_form(request):

    # Require logins. Clients will be artifically logged in
    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    # Require approver credentials, unless downloading as a client
    if not Profile.objects.get(user=request.user).approver:
        return django.http.HttpResponseRedirect('/index/')

    # Get requests should not be reaching this point
    if request.method == 'GET':
        return render(request, 'uploadnet.html', {})

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                             OPENBENCH SCRIPTING                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

@csrf_exempt
def scripts(request):

    login(request) # All requests are attached to a User

    if request.POST['action'] == 'UPLOAD_NETWORK':
        engine = request.POST['engine']
        name   = request.POST['name']
        return networks(request, engine, 'upload', name)

    if request.POST['action'] == 'CREATE_TEST':
        return create_test(request)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                              CLIENT HOOK VIEWS                              #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def client_verify_worker(request):

    ## Returns the machine, or None. Returns a JsonResponse or None.
    ## Presence of a JsonResponse indicates a failure to verify

    # Get the machine, assuming it exists
    try: machine = Machine.objects.get(id=int(request.POST['machine_id']))
    except: return None, JsonResponse({ 'error' : 'Bad Machine Id' })

    # Ensure the Client is using the same version as the Server
    if machine.info['client_ver'] != OPENBENCH_CONFIG['client_version']:
        expected_ver = OPENBENCH_CONFIG['client_version']
        return machine, JsonResponse({ 'error' : 'Bad Client Version: Expected %s' % (expected_ver)})

    # Use the secret token as our soft verification
    if machine.secret != request.POST['secret']:
        return machine, JsonResponse({ 'error' : 'Invalid Secret Token' })

    return machine, None

@csrf_exempt
def client_get_files(request):

    ## Location of static compile of Cutechess for Windows and Linux.
    ## OpenBench does not serve these files, but points to a repo ideally.

    return JsonResponse( {'location' : OPENBENCH_CONFIG['corefiles'] })

@csrf_exempt
def client_get_build_info(request):

    ## Information pulled from the config about how to build each engine.
    ## Toss in a private flag as well to indicate the need for Github Tokens.

    data = {}
    for engine, config in OPENBENCH_CONFIG['engines'].items():
        data[engine] = config['build']
        data[engine]['private'] = config['private']
    return JsonResponse(data)

@csrf_exempt
def client_worker_info(request):

    # Verify the User's credentials
    try: user = authenticate(request, True)
    except UnableToAuthenticate:
        return JsonResponse({ 'error' : 'Bad Credentials' })

    # Attempt to fetch the Machine, or create a new one
    info    = json.loads(request.POST['system_info'])
    machine = OpenBench.utils.get_machine(info['machine_id'], user, info)

    # Indicate invalid request
    if not machine:
        return JsonResponse({ 'error' : 'Bad Machine Id' })

    # Save the machine's latest information and Secret Token for this session
    machine.info   = info
    machine.secret = secrets.token_hex(32)

    # Tag engines that the Machine can build and/or run with binaries
    machine.info['supported'] = []
    for engine, data in OPENBENCH_CONFIG['engines'].items():

        # Must have all CPU flags, for both Public and Private engines
        if any([flag not in machine.info['cpu_flags'] for flag in data['build']['cpuflags']]):
            continue

        # Private engines must have, or think they have, a Git Token
        if data['private'] and engine not in machine.info['tokens'].keys():
            continue

        # Public engines must have a compiler of a sufficient version
        if not data['private'] and engine not in machine.info['compilers'].keys():
            continue

        # Must match the Operating Systems supported by the engine
        if machine.info['os_name'] not in data['build']['systems']:
            continue

        # All requirements are met, and this Machine can play with the given engine
        machine.info['supported'].append(engine)

    # Finish up
    machine.save()

    # Pass back the Machine Id, and Secret Token for this session
    return JsonResponse({ 'machine_id' : machine.id, 'secret' : machine.secret })

@csrf_exempt
def client_get_workload(request):

    # Pass along any error messages if they appear
    machine, response = client_verify_worker(request)
    if response != None: return response

    # Contains keys 'workload', otherwise none
    return JsonResponse(OpenBench.utils.get_workload(machine))

@csrf_exempt
def client_get_network(request, engine, name):

    # Verify the User's credentials
    try: django.contrib.auth.login(request, authenticate(request, True))
    except UnableToAuthenticate: return HttpResponse('Bad Credentials')

    # Return the requested Neural Network file for the Client
    return networks(request, engine, 'DOWNLOAD', name, client=True)

@csrf_exempt
def client_wrong_bench(request):

    # Pass along any error messages if they appear
    machine, response = client_verify_worker(request)
    if response != None: return response

    # Find and stop the test with the bad bench
    if int(request.POST['wrong']) != 0:
        test = Test.objects.get(id=int(request.POST['test_id']))
        test.finished = True; test.save()

    # Collect information on the Error
    wrong   = int(request.POST['wrong'])
    correct = int(request.POST['correct'])
    name    = request.POST['engine']

    # Log the error into the Events table
    LogEvent.objects.create(
        author     = machine.user.username,
        summary    = 'Got %d Expected %d for %s' % (wrong, correct, name),
        log_file   = '',
        machine_id = int(request.POST['machine_id']),
        test_id    = int(request.POST['test_id']))

    return JsonResponse({})

@csrf_exempt
def client_submit_nps(request):

    # Pass along any error messages if they appear
    machine, response = client_verify_worker(request)
    if response != None: return response

    # Update the NPS counters for the GUI views
    machine.mnps      = float(request.POST['nps'     ]) / 1e6;
    machine.dev_mnps  = float(request.POST['dev_nps' ]) / 1e6;
    machine.base_mnps = float(request.POST['base_nps']) / 1e6;
    machine.save()

    # Pass back an empty JSON response
    return JsonResponse({})

@csrf_exempt
def client_submit_error(request):

    ## Report an error when working on test. This could be one three kinds.
    ## 1. Error building the engine. Does not compile, for whatever reason.
    ## 2. Error getting the artifacts. Does not exist, lacks credentials.
    ## 3. Error during actual gameplay. Timeloss, Disconnect, Crash, etc.

    # Pass along any error messages if they appear
    machine, response = client_verify_worker(request)
    if response != None: return response

    # Flag the Test as having an error except for time losses
    test = Test.objects.get(id=int(request.POST['test_id']))
    if 'loses on time' not in request.POST['error']:
        test.error = True; test.save()

    # Log the Error into the Events table
    event = LogEvent.objects.create(
        author     = machine.user.username,
        summary    = request.POST['error'],
        log_file   = '',
        machine_id = int(request.POST['machine_id']),
        test_id    = int(request.POST['test_id']))

    # Save the Logs to /Media/ to be viewed later
    logfile = ContentFile(request.POST['logs'])
    FileSystemStorage().save('event%d.log' % (event.id), logfile)
    event.log_file = 'event%d.log' % (event.id); event.save()

    return JsonResponse({})

@csrf_exempt
def client_submit_results(request):

    # Pass along any error messages if they appear
    machine, response = client_verify_worker(request)
    if response != None: return response

    # Returns {}, or { 'stop' : True }
    return JsonResponse(OpenBench.utils.update_test(request, machine))

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                BUSINESS VIEWS                               #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def buyEthereal(request):
    return render(request, 'buyEthereal.html')