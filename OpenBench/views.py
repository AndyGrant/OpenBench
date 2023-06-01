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

import os, hashlib, datetime, json, secrets, re

import django.http
import django.shortcuts
import django.contrib.auth

import OpenBench.config
import OpenBench.utils

from OpenBench.models import *
from django.contrib.auth.models import User
from OpenSite.settings import MEDIA_ROOT

from wsgiref.util import FileWrapper
from django.db.models import F
from django.http import HttpResponse, FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from htmlmin.decorators import not_minified_response

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                              GENERAL UTILITIES                              #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

class UnableToAuthenticate(Exception):
    pass

def render(request, template, content={}, always_allow=False):

    data = content.copy()
    data.update({'config' : OpenBench.config.OPENBENCH_CONFIG})

    if OpenBench.config.REQUIRE_LOGIN_TO_VIEW:
        if not request.user.is_authenticated and not always_allow:
            return login(request, OpenBench.config.OPENBENCH_CONFIG['error']['requires_login'])

    if request.user.is_authenticated:

        profile = Profile.objects.filter(user=request.user)
        data.update({'profile' : profile.first()})

        if profile.first() and not profile.first().enabled:
            data.update({'error' : data['config']['error']['disabled']})

        if request.user.is_authenticated and not profile.first():
            data.update({'error' : data['config']['error']['fakeuser']})

    return django.shortcuts.render(request, 'OpenBench/{0}'.format(template), data)

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

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return the HTML template used for registering a new User        #
    #                                                                         #
    #  POST : Enforce matching alpha-numeric passwords, and then attempt to   #
    #         generate a new User and Profile. Return to the homepage after   #
    #         after logging the User in. Share any errors with the viewer     #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if request.method == 'GET':
        if not OpenBench.config.REQUIRE_MANUAL_REGISTRATION:
            return render(request, 'register.html', always_allow=True)
        return login(request, OpenBench.config.OPENBENCH_CONFIG['error']['manual_registration'])

    if request.POST['password1'] != request.POST['password2']:
        return index(request, error='Passwords Do Not Match')

    if not request.POST['username'].isalnum():
        return index(request, error='Alpha Numeric Usernames Only')

    if User.objects.filter(username=request.POST['username']):
        return index(request, error='That Username is taken')

    email    = request.POST['email']
    username = request.POST['username']
    password = request.POST['password1']

    user = User.objects.create_user(username, email, password)
    django.contrib.auth.login(request, user)
    Profile.objects.create(user=user)

    return django.http.HttpResponseRedirect('/index/')

def login(request, error=''):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return the HTML template used for logging in a User             #
    #                                                                         #
    #  POST : Attempt to login the User. If their login is invalid, let them  #
    #         know. In all cases, return the User back to the main page       #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if request.method == 'GET' or error:
        data = { 'error' : error }
        return render(request, 'login.html', data, always_allow=True)

    try:
        user = authenticate(request)
        django.contrib.auth.login(request, user)
        return django.http.HttpResponseRedirect('/index/')

    except UnableToAuthenticate:
        data = { 'error' : 'Unable to authenticate username and password' }
        return render(request, 'login.html', data, always_allow=True)

def logout(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Logout the User if they are logged in. Return to the main page  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    django.contrib.auth.logout(request)
    return django.http.HttpResponseRedirect('/index/')

def profile(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : If the User is logged in, return the HTML template which shows  #
    #         all of the information about the User, and a form to change the #
    #         email address, password, and default engine of the User. If the #
    #         User is not logged in, return them to the main page             #
    #                                                                         #
    #  POST : Modify the User's email address and selected Engine, if the     #
    #         User has requested this. Update the password for the User if    #
    #         they have requested a change and provided a new set of matching #
    #         passwords. Return the User to the main page                     #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    if request.method == 'GET':
        return render(request, 'profile.html')

    profile = Profile.objects.filter(user=request.user)
    profile.update(engine=request.POST['engine'], repo=request.POST['repo'])

    request.user.email = request.POST['email']
    request.user.save()

    if request.POST['password1'] != request.POST['password2']:
        return index(request, error='Passwords Do Not Match')

    if request.POST['password1'] != '':
        request.user.set_password(request.POST['password1'])
        django.contrib.auth.login(request, request.user)
        request.user.save()

    return django.http.HttpResponseRedirect('/index/')


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                               TEST LIST VIEWS                               #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def index(request, page=1, error=''):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return all pending, active, and completed tests. Limit the      #
    #         display of tests by the requested page number. Also display the #
    #         status for connected machines.                                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    pending   = OpenBench.utils.get_pending_tests()
    active    = OpenBench.utils.get_active_tests()
    completed = OpenBench.utils.get_completed_tests()
    awaiting  = OpenBench.utils.get_awaiting_tests()

    start, end, paging = OpenBench.utils.getPaging(completed, page, 'index')

    data = {
        'pending'   : pending,              'active'   : active,
        'completed' : completed[start:end], 'awaiting' : awaiting,
        'paging'    : paging,               'status'   : OpenBench.utils.getMachineStatus(),
        'error'     : error,
    }

    return render(request, 'index.html', data)

def greens(request, page=1):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return all tests both passed and completed. Limit the display   #
    #         of tests by the requested page number.                          #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    completed = OpenBench.utils.get_completed_tests().filter(passed=True)
    start, end, paging = OpenBench.utils.getPaging(completed, page, 'greens')

    data = {'completed' : completed[start:end], 'paging' : paging}
    return render(request, 'index.html', data)

def search(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return the HTML template for searching tests on the framework.  #
    #                                                                         #
    #  POST : Filter the tests by the provided criteria, and return a display #
    #         with the filtered results. Keywords are case insensitive        #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if request.method == 'GET':
        return render(request, 'search.html', {})

    tests = Test.objects.all()
    keywords = request.POST['keywords'].upper().split()
    if not keywords: keywords = [""]

    if request.POST['engine'] != '':
        tests = tests.filter(engine=request.POST['engine'])

    if request.POST['author'] != '':
        tests = tests.filter(author=request.POST['author'])

    if request.POST['showgreens'] == 'False':
        tests = tests.exclude(passed=True)

    if request.POST['showyellows'] == 'False':
        tests = tests.exclude(failed=True, wins__gte=F('losses'))

    if request.POST['showreds'] == 'False':
        tests = tests.exclude(failed=True, wins__lt=F('losses'))

    if request.POST['showunfinished'] == 'False':
        tests = tests.exclude(passed=False, failed=False)

    if request.POST['showdeleted'] == 'False':
        tests = tests.exclude(deleted=True)

    filtered = [
        test for test in tests.order_by('-updated') if
        any(keyword in test.dev.name.upper() for keyword in keywords)
    ]

    return render(request, 'search.html', {'tests' : filtered})

def user(request, username, page=1):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return all pending, active, and completed tests for the User    #
    #         that has been requested. Limit the display of completed tests   #
    #         by the requested page number. Also display the User's machines  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    pending   = OpenBench.utils.get_pending_tests().filter(author=username)
    active    = OpenBench.utils.get_active_tests().filter(author=username)
    completed = OpenBench.utils.get_completed_tests().filter(author=username)
    awaiting  = OpenBench.utils.get_awaiting_tests().filter(author=username)

    url = 'user/{0}'.format(username)
    start, end, paging = OpenBench.utils.getPaging(completed, page, url)

    data = {
        'pending'   : pending,              'active'   : active,
        'completed' : completed[start:end], 'awaiting' : awaiting,
        'paging'    : paging,               'status'   : OpenBench.utils.getMachineStatus(username),
    }

    return render(request, 'index.html', data)

def event(request, id):

    try:
        with open(os.path.join(MEDIA_ROOT, LogEvent.objects.get(id=id).log_file)) as fin:
            return render(request, 'event.html', { 'content' : fin.read() })
    except:
        return HttpResponseRedirect('/index/')

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                           GENERAL DATA TABLE VIEWS                          #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def users(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return information about all users on the Framework. Sort the   #
    #         Users by games completed, tests created. The HTML template will #
    #         filter out disabled users later.                                #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    data = {'profiles' : Profile.objects.order_by('-games', '-tests')}
    return render(request, 'users.html', data)

def events_actions(request, page=1):

    events = LogEvent.objects.all().filter(machine_id=0).order_by('-id')
    start, end, paging = OpenBench.utils.getPaging(events, page, 'events')

    data = {'events' : events[start:end], 'paging' : paging};
    return render(request, 'events.html', data)

def events_errors(request, page=1):

    events = LogEvent.objects.all().exclude(machine_id=0).order_by('-id')
    start, end, paging = OpenBench.utils.getPaging(events, page, 'errors')

    data = {'events' : events[start:end], 'paging' : paging};
    return render(request, 'errors.html', data)

def machines(request, machineid=None):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return information about all of the machines that have been     #
    #         active on the Framework within the last fifteen minutes         #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if machineid == None:
        data = {'machines' : OpenBench.utils.getRecentMachines()}
        return render(request, 'machines.html', data)

    else:
        data = {'machine' : OpenBench.models.Machine.objects.get(id=machineid)}
        return render(request, 'machine.html', data)


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                            TEST MANAGEMENT VIEWS                            #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def test(request, id, action=None):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : The User is either trying to view the status of the selected    #
    #         test, or adjust the running state of the test in some way. When #
    #         viewing a test, collect the results and return an HTML template #
    #         using that data. Otherwise, look to adjust the running state of #
    #         the test. We throw out any invalid requests. Create a LogEvent  #
    #         if the we attempt to modify the test's state in any way         #
    #                                                                         #
    #  POST : The only valid POST request is for the action MODIFY. Requests  #
    #         to modify contain an updated Priority and Throughput parameter  #
    #         for the selected test. Bound the updated values, and log the    #
    #         modification of the test with the creation of a new LogEvent    #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if not Test.objects.filter(id=id):
        return django.http.HttpResponseRedirect('/index/')

    if action not in ['APPROVE', 'RESTART', 'STOP', 'DELETE', 'MODIFY']:

        # Select the Test, and all Result objects attached
        test    = Test.objects.get(id=id)
        results = Result.objects.filter(test=test).order_by('machine_id')
        data    = { 'test' : test, 'results': {} }

        for result in results:

            # Insert the Result into the results
            if result.machine.id not in data['results'].keys():
                data['results'][result.machine.id] = {
                    'games'      : 0, 'wins'       : 0,
                    'losses'     : 0, 'draws'      : 0,
                    'timeloss'   : 0, 'crashes'    : 0,
                }

            # Always use the latest Time stamp, by virtue of sorting Results
            data['results'][result.machine.id]['machine_id'] = result.machine.id
            data['results'][result.machine.id]['username'  ] = result.machine.user.username
            data['results'][result.machine.id]['updated'   ] = result.updated

            # Sum up all results from a given machine into a single value
            data['results'][result.machine.id]['games'     ] += result.games
            data['results'][result.machine.id]['wins'      ] += result.wins
            data['results'][result.machine.id]['losses'    ] += result.losses
            data['results'][result.machine.id]['draws'     ] += result.draws
            data['results'][result.machine.id]['timeloss'  ] += result.timeloss
            data['results'][result.machine.id]['crashes'   ] += result.crashes

        return render(request, 'test.html', data)

    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    user = request.user
    test = Test.objects.get(id=id)
    profile = Profile.objects.get(user=user)

    if not profile.approver and test.author != profile.user.username:
        return django.http.HttpResponseRedirect('/index/')

    if action == 'APPROVE':
        if test.author == user.username and not user.is_superuser:
            return django.http.HttpResponseRedirect('/index/')

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
    LogEvent.objects.create(author=user.username, summary=action, log_file='', test_id=test.id)
    return django.http.HttpResponseRedirect('/index/')

def newTest(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return the HTML template for creating a new test when the User  #
    #         is both logged in, and enabled. Otherwise, we redirect those    #
    #         requests to either login, or the index where they are told that #
    #         their account has not yet been enabled                          #
    #                                                                         #
    #  POST : Enabled Users may create new tests. Fields are error checked.   #
    #         If an error is found, the creation is aborted and the list of   #
    #         errors is prestented back to the User on the homepage. If both  #
    #         versions of the Engine in the Test have been seen, then we will #
    #         automatically approve the Test                                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    if not Profile.objects.get(user=request.user).enabled:
        return django.http.HttpResponseRedirect('/index/')

    if request.method == 'GET':
        data = { 'networks' : list(Network.objects.all().values()) }
        return render(request, 'newTest.html', data)

    test, errors = OpenBench.utils.create_new_test(request)
    if errors != [] and errors != None:
        errors = ["[{0}]: {1}".format(i, e) for i, e in enumerate(errors)]
        longest = max([len(e) for e in errors])
        errors = ["{0}{1}".format(e, ' ' * (longest-len(e))) for e in errors]
        return index(request, error='\n'.join(errors))

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

    return django.http.HttpResponseRedirect('/index/')


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                          NETWORK MANAGEMENT VIEWS                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

def networks(request, action=None, sha256=None, client=False):

    # *** GET Requests:
    # [1] Fetch a view of all the Networks on the framework (/networks/)
    # [2] Fetch a view of all Networks for a given engine (/networks/<engine>/)
    # [3] Download the contents of a Network if allowed (/networks/download/<sha256>/)
    #
    # *** POST Requests:
    # [1] Upload a Network to the framework (/networks/upload/)
    # [2] Set as default a Network on the framework (/networks/default/<sha256>/)
    # [3] Delete a Network from the framework (/networks/delete/<sha256>/)
    #
    # *** Rights:
    # Any user may look at the list of Networks, for all or some engines
    # Only authenticated and approved Users may interact in the remaining ways

    if not action or action.upper() not in ['UPLOAD', 'DEFAULT', 'DELETE', 'DOWNLOAD']:
        networks = Network.objects.all()
        if action: networks = networks.filter(engine=action)
        return render(request, 'networks.html', { 'networks' : networks.order_by('-id') })

    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    if not client and not Profile.objects.get(user=request.user).approver:
        return django.http.HttpResponseRedirect('/index/')

    if action.upper() == 'UPLOAD':

        if request.method == 'GET':
            return render(request, 'uploadnet.html', {})

        name    = request.POST['name']
        engine  = request.POST['engine']
        netfile = request.FILES['netfile']
        sha256  = hashlib.sha256(netfile.file.read()).hexdigest()[:8].upper()

        if not re.match(r'^[a-zA-Z0-9_.-]+$', name):
            return index(request, error='Name may only contain letters, numbers, dashes, underscores, and dots')

        if Network.objects.filter(sha256=sha256):
            return index(request, error='Network with that hash already exists')

        if Network.objects.filter(engine=engine, name=sha256):
            return index(request, error='Network with that name already exists for that engine')

        if engine not in OpenBench.utils.OPENBENCH_CONFIG['engines'].keys():
            return index(request, error='No Engine found with matching name')

        FileSystemStorage().save(sha256, netfile)

        Network.objects.create(
            sha256=sha256, name=name,
            engine=engine, author=request.user.username)

        return index(request)

    if action.upper() == 'DEFAULT':

        if not Network.objects.filter(sha256=sha256):
            return index(request, error='No Network found with matching SHA256')

        network = Network.objects.get(sha256=sha256)
        Network.objects.filter(engine=network.engine).update(default=False)
        network.default = True; network.save()

        return django.http.HttpResponseRedirect('/networks/')

    if action.upper() == 'DELETE':

        if not Network.objects.filter(sha256=sha256):
            return index(request, error='No Network found with matching SHA256')

        Network.objects.get(sha256=sha256).delete()
        FileSystemStorage().delete(sha256)

        return django.http.HttpResponseRedirect('/networks/')

    if action.upper() == 'DOWNLOAD':

        if not Network.objects.filter(sha256=sha256):
            return index(request, error='No Network found with matching SHA256')

        netfile  = os.path.join(MEDIA_ROOT, sha256)
        fwrapper = FileWrapper(open(netfile, 'rb'), 8192)
        response = FileResponse(fwrapper, content_type='application/octet-stream')

        response['Expires'] = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).ctime()
        response['Content-Length'] = os.path.getsize(netfile)
        response['Content-Disposition'] = 'attachment; filename=' + sha256
        return response


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                             OPENBENCH SCRIPTING                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

@csrf_exempt
def scripts(request):

    login(request) # All requests are attached to a User

    if request.POST['action'] == 'UPLOAD':
        return networks(request, action='UPLOAD')

    if request.POST['action'] == 'CREATE_TEST':
        return newTest(request)

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
    if machine.info['client_ver'] != OpenBench.config.OPENBENCH_CONFIG['client_version']:
        expected_ver = OpenBench.config.OPENBENCH_CONFIG['client_version']
        return machine, JsonResponse({ 'error' : 'Bad Client Version: Expected %s' % (expected_ver)})

    # Use the secret token as our soft verification
    if machine.secret != request.POST['secret']:
        return machine, JsonResponse({ 'error' : 'Invalid Secret Token' })

    return machine, None

@csrf_exempt
def client_get_files(request):

    ## Location of static compile of Cutechess for Windows and Linux.
    ## OpenBench does not serve these files, but points to a repo ideally.

    return JsonResponse( {'location' : OpenBench.config.OPENBENCH_CONFIG['corefiles'] })

@csrf_exempt
def client_get_build_info(request):

    ## Information pulled from the config about how to build each engine.
    ## Toss in a private flag as well to indicate the need for Github Tokens.

    data = {}
    for engine, config in OpenBench.config.OPENBENCH_CONFIG['engines'].items():
        data[engine] = config['build']
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
    for engine, data in OpenBench.config.OPENBENCH_CONFIG['engines'].items():

        # Must have all CPU flags, for both Public and Private engines
        if any([flag not in machine.info['cpu_flags'] for flag in data['build']['cpuflags']]):
            continue

        # Private engines must have, or think they have, a Git Token
        if data['private'] and engine not in machine.info['tokens'].keys():
            continue

        # Public engines must have a compiler of a sufficient version
        if not data['private'] and engine not in machine.info['compilers'].keys():
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
def client_get_network(request, identifier, engine=None):

    # Verify the User's credentials
    try: django.contrib.auth.login(request, authenticate(request, True))
    except UnableToAuthenticate: return HttpResponse('Bad Credentials')

    # Return the requested Neural Network, after resolving the Network name
    if engine is not None:
        try: sha256 = Network.objects.get(name=identifier, engine=engine).sha256
        except: return HttpResponse('Unable to find associated Network')
        return networks(request, action='DOWNLOAD', sha256=sha256, client=True)

    # Return the requested Neural Network file for the Client
    return networks(request, action='DOWNLOAD', sha256=identifier, client=True)

@csrf_exempt
def client_wrong_bench(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  POST : Inform the server that an Engine reported an incorrect Bench    #
    #         value during the init process for a Test. We stop the Test and  #
    #         log an Error into the Events table to indicate what happened    #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

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

    # Update the NPS counter for the GUI views
    machine.mnps = float(request.POST['nps']) / 1e6; machine.save()

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