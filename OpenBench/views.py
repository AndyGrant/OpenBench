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

from OpenBench.workloads.create_workload import create_workload
from OpenBench.workloads.get_workload import get_workload
from OpenBench.workloads.modify_workload import modify_workload
from OpenBench.workloads.verify_workload import verify_workload
from OpenBench.workloads.view_workload import view_workload

from OpenBench.config import OPENBENCH_CONFIG, OPENBENCH_STATIC_VERSION
from OpenSite.settings import PROJECT_PATH

from OpenBench.models import *
from django.contrib.auth.models import User
from OpenSite.settings import MEDIA_ROOT

from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.utils import timezone

from wsgiref.util import FileWrapper

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                              GENERAL UTILITIES                              #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

ERROR_MESSAGES = {
    'disabled'            : 'Account has not been enabled. Contact an Administrator',
    'fakeuser'            : 'This is not a real OpenBench User. Create an OpenBench account',
    'requires_login'      : 'All pages require a user login to access',
    'manual_registration' : 'Registration can only be done via an Administrator',
}

class UnableToAuthenticate(Exception):
    pass

def render(request, template, content={}, always_allow=False, error=None, warning=None, status=None):

    data = content.copy()
    data.update({ 'config' : OPENBENCH_CONFIG })
    data.update({ 'static_version' : OPENBENCH_STATIC_VERSION })

    if OPENBENCH_CONFIG['require_login_to_view']:
        if not request.user.is_authenticated and not always_allow:
            return redirect(request, '/login/',  error=ERROR_MESSAGES['requires_login'])

    if request.user.is_authenticated:

        profile = Profile.objects.filter(user=request.user)
        data.update({'profile' : profile.first()})

        if profile.first() and not profile.first().enabled:
            request.session['error_message'] = ERROR_MESSAGES['disabled']

        elif request.user.is_authenticated and not profile.first():
            request.session['error_message'] = ERROR_MESSAGES['fakeuser']

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
        if not OPENBENCH_CONFIG['require_manual_registration']:
            return render(request, 'register.html', always_allow=True)
        return redirect(request, '/login/', error=ERROR_MESSAGES['manual_registration'])

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

    for (engine, current_repo) in profile.repos.items():
        repo_name = request.POST.get('engine-repo-%s' % (engine), '').removesuffix('/')
        repo = 'https://github.com/%s' % (repo_name)

        if repo != current_repo and repo_name:
            changes += 'Updated Engine: %s to use %s\n' % (engine, repo)
            profile.repos[engine] = repo

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
    return render(request, 'search.html', { 'tests' : reversed(filtered) }, error=error)

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

    # Request is to modify or interact with the Test
    if action != None:
        return modify_workload(request, id, action)

    # Verify that the Test id exists
    if not (test := Test.objects.filter(id=id).first()):
        return redirect(request, '/index/', error='No such Test exists')

    # Verify that it is indeed a Test and not a Tune
    if test.test_mode == 'TUNE':
        return redirect(request, '/tune/%d' % (id))

    # Verify that it is indeed a Test and not Datagen
    if test.test_mode == 'DATAGEN':
        return redirect(request, '/datagen/%d' % (id))

    return view_workload(request, test, 'TEST')

def tune(request, id, action=None):

    # Request is to modify or interact with the Tune
    if action != None:
        return modify_workload(request, id, action)

    # Verify that the Tune id exists
    if not (tune := Test.objects.filter(id=id).first()):
        return redirect(request, '/index/', error='No such Tune exists')

    # Verify that it is indeed a Tune and not a Test
    if tune.test_mode == 'SPRT' or tune.test_mode == 'GAMES':
        return redirect(request, '/test/%d' % (id))

    # Verify that it is indeed a Tune and not Datagen
    if tune.test_mode == 'DATAGEN':
        return redirect(request, '/datagen/%d' % (id))

    return view_workload(request, tune, 'TUNE')

def datagen(request, id, action=None):

    # Request is to modify or interact with the Datagen
    if action != None:
        return modify_workload(request, id, action)

    # Verify that the Datagen id exists
    if not (datagen := Test.objects.filter(id=id).first()):
        return redirect(request, '/index/', error='No such Datagen exists')

    # Verify that it is indeed a Datagen and not a Tune
    if datagen.test_mode == 'TUNE':
        return redirect(request, '/tune/%d' % (id))

    # Verify that it is indeed a Datagen and not a Test
    if datagen.test_mode == 'SPRT' or datagen.test_mode == 'GAMES':
        return redirect(request, '/test/%d' % (id))

    return view_workload(request, datagen, 'DATAGEN')

def create_test(request):
    return create_workload(request, 'TEST')

def create_tune(request):
    return create_workload(request, 'TUNE')

def create_datagen(request):
    return create_workload(request, 'DATAGEN')

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                          NETWORK MANAGEMENT VIEWS                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def networks(request, engine=None, action=None, name=None, client=False):

    # Without an identifier and a valid action, all we can do is view the list
    if not name or action.upper() not in ['UPLOAD', 'DEFAULT', 'DELETE', 'DOWNLOAD', 'EDIT']:
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
        'EDIT'     : OpenBench.utils.network_edit,
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

def verify_worker(function):

    def wrapped_verify_worker(*args, **kwargs):

        # Get the machine, assuming it exists
        try: machine = Machine.objects.get(id=int(args[0].POST['machine_id']))
        except: return JsonResponse({ 'error' : 'Bad Machine Id' })

        # Ensure the Client is using the same version as the Server
        if machine.info['client_ver'] != OPENBENCH_CONFIG['client_version']:
            expected_ver = OPENBENCH_CONFIG['client_version']
            return JsonResponse({ 'error' : 'Bad Client Version: Expected %d' % (expected_ver)})

        # Use the secret token as our soft verification
        if machine.secret != args[0].POST['secret']:
            return JsonResponse({ 'error' : 'Invalid Secret Token' })

        # Otherwise, carry on, and pass along the machine
        return function(*args, machine)

    return wrapped_verify_worker

@csrf_exempt
def client_version_ref(request):

    # Verify the User's credentials
    try: user = authenticate(request, True)
    except UnableToAuthenticate:
        return JsonResponse({ 'error' : 'Bad Credentials' })

    # Enough information to download the right Client
    return JsonResponse({
        'client_version'  : OPENBENCH_CONFIG['client_version' ],
        'client_repo_url' : OPENBENCH_CONFIG['client_repo_url'],
        'client_repo_ref' : OPENBENCH_CONFIG['client_repo_ref'],
    })

@csrf_exempt
def client_get_build_info(request):

    ## Information pulled from the config about how to build each engine.
    ## Toss in a private flag as well to indicate the need for Github Tokens.

    data = {}
    for engine, config in OPENBENCH_CONFIG['engines'].items():
        data[engine] = config['build'].copy()
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
def client_get_network(request, engine, name):

    # Verify the User's credentials
    try: django.contrib.auth.login(request, authenticate(request, True))
    except UnableToAuthenticate: return HttpResponse('Bad Credentials')

    # Return the requested Neural Network file for the Client
    return networks(request, engine, 'DOWNLOAD', name, client=True)

@csrf_exempt
@verify_worker
def client_get_workload(request, machine):
    return JsonResponse(get_workload(request, machine))

@csrf_exempt
@verify_worker
def client_bench_error(request, machine):

    # Find and stop the test with the bad bench
    test = Test.objects.get(id=int(request.POST['test_id']))
    test.finished = True; test.save()

    # Log the error into the Events table
    LogEvent.objects.create(
        author     = machine.user.username,
        summary    = request.POST['error'],
        log_file   = '',
        machine_id = int(request.POST['machine_id']),
        test_id    = int(request.POST['test_id']))

    return JsonResponse({})

@csrf_exempt
@verify_worker
def client_submit_nps(request, machine):

    # Update the NPS counters for the GUI views
    machine.mnps      = float(request.POST['nps'     ]) / 1e6;
    machine.dev_mnps  = float(request.POST['dev_nps' ]) / 1e6;
    machine.base_mnps = float(request.POST['base_nps']) / 1e6;
    machine.save()

    # Pass back an empty JSON response
    return JsonResponse({})

@csrf_exempt
@verify_worker
def client_submit_error(request, machine):

    ## Report an error when working on test. This could be one three kinds.
    ## 1. Error building the engine. Does not compile, for whatever reason.
    ## 2. Error getting the artifacts. Does not exist, lacks credentials.
    ## 3. Error during actual gameplay. Timeloss, Disconnect, Crash, etc.

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
@verify_worker
def client_submit_results(request, machine):

    # Returns {}, or { 'stop' : True }
    return JsonResponse(OpenBench.utils.update_test(request, machine))

@csrf_exempt
@verify_worker
def client_heartbeat(request, machine):

    # Force a refresh of the updated timestamp
    machine.save()

    # Include a 'stop' header iff the test was finished
    test = Test.objects.get(id=int(request.POST['test_id']))
    return JsonResponse([{}, { 'stop' : True }][test.finished])

@csrf_exempt
@verify_worker
def client_submit_pgn(request, machine):

    with transaction.atomic():

        # Format: test.result.book-index.pgn.bz2
        pgn            = PGN()
        pgn.test_id    = int(request.POST['test_id']   )
        pgn.result_id  = int(request.POST['result_id'] )
        pgn.book_index = int(request.POST['book_index'])
        pgn.save()

        # Save the .pgn.bz2 to /Media/
        FileSystemStorage().save(pgn.filename(), ContentFile(request.FILES['file'].read()))

    return JsonResponse({})

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def api_response(data):
    return HttpResponse(json.dumps(data, indent=4), content_type='application/json')

@csrf_exempt
def api_authenticate(request, require_enabled=False):

    try:

        # Force requiring an enabled user when require_login_to_view is set
        require_enabled = require_enabled or OPENBENCH_CONFIG['require_login_to_view']

        # Don't require a login for Public frameworks
        if not require_enabled:
            return True

        # Request is made from a browser, and is already logged in
        if request.user.is_authenticated:
            return Profile.objects.get(user=request.user).enabled

        # Request might be made from the command line. Check the headers
        user = django.contrib.auth.authenticate(
            username=request.POST['username'], password=request.POST['password'])
        return Profile.objects.get(user=user).enabled

    except Exception:
        import traceback
        traceback.print_exc()
        return False

@csrf_exempt
def api_configs(request, engine=None):

    if not api_authenticate(request):
        return api_response({ 'error' : 'API requires authentication for this server' })

    if engine == None:
        engines = list(OPENBENCH_CONFIG['engines'].keys())
        books   = OPENBENCH_CONFIG['books']
        return api_response({ 'engines' : engines, 'books' : books })

    if engine in OPENBENCH_CONFIG['engines'].keys():
        return api_response(OPENBENCH_CONFIG['engines'][engine])

    return api_response({ 'error' : 'Engine not found. Check /api/config/ for a full list' })

@csrf_exempt
def api_networks(request, engine):

    if not api_authenticate(request):
        return api_response({ 'error' : 'API requires authentication for this server' })

    if engine in OPENBENCH_CONFIG['engines'].keys():

        if not (network := Network.objects.filter(engine=engine, default=True).first()):
            return api_response({ 'error' : 'Engine does not have a default Network' })

        default = {
            'sha'    : network.sha256, 'name'    : network.name,
            'author' : network.author, 'created' : str(network.created) }

        networks = [
          { 'sha'    : network.sha256, 'name'    : network.name,
            'author' : network.author, 'created' : str(network.created) }
            for network in Network.objects.filter(engine=engine) ]

        return api_response({ 'default' : default, 'networks' : networks })

    else:
        return api_response({ 'error' : 'Engine not found. Check /api/config/ for a full list' })

@csrf_exempt
def api_network_download(request, engine, identifier):

    if not api_authenticate(request):
        return api_response({ 'error' : 'API requires authentication for this server' })

    if not api_authenticate(request, require_enabled=True):
        return api_response({ 'error' : 'API requires authentication for this endpoint' })

    if (network := Network.objects.filter(engine=engine, sha256=identifier).first()):
        return OpenBench.utils.network_download(request, engine, network)

    if (network := Network.objects.filter(engine=engine, name=identifier).first()):
        return OpenBench.utils.network_download(request, engine, network)

    return api_response({ 'error' : 'Engine not found. Check /api/config/ for a full list' })

@csrf_exempt
def api_build_info(request):

    if not api_authenticate(request):
        return api_response({ 'error' : 'API requires authentication for this server' })

    data = {}
    for engine, config in OPENBENCH_CONFIG['engines'].items():
        data[engine] = config

    for network in Network.objects.filter(default=True):

        if network.engine not in data:
            continue

        data[network.engine]['network'] = {
            'sha'     : network.sha256,
            'name'    : network.name,
            'author'  : network.author,
            'created' : str(network.created)
        }

    return api_response(data)

@csrf_exempt
def api_pgns(request, pgn_id):

    if not api_authenticate(request):
        return api_response({ 'error' : 'API requires authentication for this server' })

    # Possible to request a PGN that does not exist
    pgn_path = FileSystemStorage('Media/PGNs').path('%d.pgn.tar' % (pgn_id))
    if not os.path.exists(pgn_path):
        return api_response({ 'error' : 'Unable to find PGN for Workload #%d' % (pgn_id) })

    # Craft the download HTML response
    fwrapper = FileWrapper(open(pgn_path, 'rb'), 8192)
    response = FileResponse(fwrapper, content_type='application/octet-stream')

    # Set all headers and return response
    response['Expires'] = -1
    response['Content-Length'] = os.path.getsize(pgn_path)
    response['Content-Disposition'] = 'attachment; filename=%d.pgn.tar' % (pgn_id)
    return response

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                BUSINESS VIEWS                               #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def buyEthereal(request):
    return render(request, 'buyEthereal.html')