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

import os, hashlib

import django.http
import django.shortcuts
import django.contrib.auth

import OpenBench.config
import OpenBench.utils

from OpenBench.models import *
from OpenSite.settings import MEDIA_ROOT

from django.contrib.auth.models import User

from django.db.models import F
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import FileSystemStorage
from htmlmin.decorators import not_minified_response

def render(request, template, content={}):

    template = 'OpenBench/{0}'.format(template)

    data = content.copy()
    data.update({'config' : OpenBench.config.OPENBENCH_CONFIG})

    if request.user.is_authenticated:

        profile = Profile.objects.filter(user=request.user)
        data.update({'profile' : profile.first()})

        if profile.first() and not profile.first().enabled:
            data.update({'error' : data['config']['error']['disabled']})

        if request.user.is_authenticated and not profile.first():
            data.update({'error' : data['config']['error']['fakeuser']})

    return django.shortcuts.render(request, template, data)


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
        return render(request, 'register.html')

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

def login(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return the HTML template used for logging in a User             #
    #                                                                         #
    #  POST : Attempt to login the User and authenticate their credentials.   #
    #         If their login is invalid, let them know. In all cases, return  #
    #         the User back to the main page                                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    if request.method == 'GET':
        return render(request, 'login.html')

    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])

    if user is None:
        return index(request, error='Unable to Authenticate User')

    django.contrib.auth.login(request, user)
    return django.http.HttpResponseRedirect('/index/')

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

    pending   = OpenBench.utils.getPendingTests()
    active    = OpenBench.utils.getActiveTests()
    completed = OpenBench.utils.getCompletedTests()

    start, end, paging = OpenBench.utils.getPaging(completed, page, 'index')

    data = {
        'error'  : error,  'pending'   : pending,
        'active' : active, 'completed' : completed[start:end],
        'paging' : paging, 'status'    : OpenBench.utils.getMachineStatus(),
    }

    return render(request, 'index.html', data)

def greens(request, page=1):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return all tests both passed and completed. Limit the display   #
    #         of tests by the requested page number.                          #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    completed = OpenBench.utils.getCompletedTests().filter(passed=True)
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

    pending   = OpenBench.utils.getPendingTests().filter(author=username)
    active    = OpenBench.utils.getActiveTests().filter(author=username)
    completed = OpenBench.utils.getCompletedTests().filter(author=username)

    url = 'user/{0}'.format(username)
    start, end, paging = OpenBench.utils.getPaging(completed, page, url)

    data = {
        'pending'   : pending,              'active' : active,
        'completed' : completed[start:end], 'paging' : paging,
        'status'    : OpenBench.utils.getMachineStatus(username),
    }

    return render(request, 'index.html', data)


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

def events(request, page=1):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return information about the events taken on the Framework.     #
    #         Only show those events for the requested page.                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    events = LogEvent.objects.all().order_by('-id')
    start, end, paging = OpenBench.utils.getPaging(events, page, 'events')

    data = {'events' : events[start:end], 'paging' : paging};
    return render(request, 'events.html', data)

def machines(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return information about all of the machines that have been     #
    #         active on the Framework within the last fifteen minutes         #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    data = {'machines' : OpenBench.utils.getRecentMachines()}
    return render(request, 'machines.html', data)

def networks(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return information about all of the Networks that have been     #
    #         uploaded to the Framework at any point in time                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    networks = Network.objects.all().order_by('-id')
    return render(request, 'networks.html', {'networks' : networks})

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
        test = Test.objects.get(id=id)
        results = Result.objects.filter(test=test).order_by('machine_id')
        data = {'test' : test, 'results': results}
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
        test.priority = int(request.POST['priority'])
        test.throughput = max(1, int(request.POST['throughput']))
        test.save()

    action += " P={0} TP={1}".format(test.priority, test.throughput)
    LogEvent.objects.create(data=action, author=user.username, test=test)
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
        return render(request, 'newTest.html')

    test, errors = OpenBench.utils.createNewTest(request)
    if errors != [] and errors != None:
        errors = ["[{0}]: {1}".format(i, e) for i, e in enumerate(errors)]
        longest = max([len(e) for e in errors])
        errors = ["{0}{1}".format(e, ' ' * (longest-len(e))) for e in errors]
        return index(request, error='\n'.join(errors))

    username = request.user.username
    profile  = Profile.objects.get(user=request.user)
    LogEvent.objects.create(data="CREATE", author=username, test=test)

    approved = Test.objects.filter(approved=True)
    A = approved.filter( dev__sha=test.dev.sha).exists()
    B = approved.filter(base__sha=test.dev.sha).exists()
    C = approved.filter( dev__sha=test.base.sha).exists()
    D = approved.filter(base__sha=test.base.sha).exists()

    if (A or B) and (C or D):
        test.approved = True; test.save()
        action = "AUTOAPP P={0} TP={1}".format(test.priority, test.throughput)
        LogEvent.objects.create(data=action, author=username, test=test)

    elif not OpenBench.config.USE_CROSS_APPROVAL and profile.approver:
        test.approved = True; test.save()
        action = "APPROVE P={0} TP={1}".format(test.priority, test.throughput)
        LogEvent.objects.create(data=action, author=username, test=test)

    return django.http.HttpResponseRedirect('/index/')

def newNetwork(request):

    if not request.user.is_authenticated:
        return django.http.HttpResponseRedirect('/login/')

    if not Profile.objects.get(user=request.user).approver:
        return django.http.HttpResponseRedirect('/index/')

    if request.method == 'GET':
        return render(request, 'uploadnet.html', {})

    engine  = request.POST['engine']
    netfile = request.FILES['netfile']
    sha256  = hashlib.sha256(netfile.file.read()).hexdigest()[:8].upper()

    if Network.objects.filter(sha256=sha256):
        return index(request, error='Network with that hash already exists')

    if engine not in OpenBench.utils.OPENBENCH_CONFIG['engines'].keys():
        return index(request, error='No Engine found with matching name')

    fsystem = FileSystemStorage()
    fname   = fsystem.save(sha256, netfile)

    Network.objects.create(
        sha256=sha256, name=request.POST['name'],
        engine=engine, author=request.user.username);

    return index(request)

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                              CLIENT HOOK VIEWS                              #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

@not_minified_response
def clientGetFiles(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return a URL pointing to the location of Cutechess-cli, as well #
    #         as any DLLs or Shared Object files needed for Cutechess-cli     #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    return HttpResponse(OpenBench.config.OPENBENCH_CONFIG['corefiles'])

@not_minified_response
def clientGetBuildInfo(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return a Dictionary of all of the Engines that are present in   #
    #         config.py, as well as the required compilation tools for them   #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    data = {} # Return all engine-compiler information
    for engine, config in OpenBench.config.OPENBENCH_CONFIG['engines'].items():
        data[engine] = config['build']['compilers']
    return HttpResponse(str(data))

@csrf_exempt
@not_minified_response
def clientGetWorkload(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  POST : Return a Dictionary of data in order to complete a workload. If #
    #         there are no tests for the User, 'None' will be returned. If we #
    #         cannot authenticate the User, 'Bad Credentials' is returned. If #
    #         the posted Machine does not belong the the User, 'Bad Machine'  #
    #         is returned.                                                    #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    # Verify the User's credentials
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # getWorkload() will verify the integrity of the request
    return HttpResponse(OpenBench.utils.getWorkload(user, request))

@csrf_exempt
@not_minified_response
def clientWrongBench(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  POST : Inform the server that an Engine reported an incorrect Bench    #
    #         value during the init process for a Test. We stop the Test and  #
    #         log an Error into the Events table to indicate what happened    #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    # Verify the User's credentials
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # Verify the Machine belongs to the User
    machine = Machine.objects.get(id=int(request.POST['machineid']))
    if machine.user != user: return HttpResponse('Bad Machine')

    # Find and stop the test with the bad bench
    if int(request.POST['wrong']) != 0:
        test = Test.objects.get(id=int(request.POST['testid']))
        test.finished = True; test.save()

    # Collect information on the Error
    wrong   = request.POST['wrong']
    correct = request.POST['correct']
    name    = request.POST['engine']

    # Format a nice Error message
    message = 'Got {0} Expected {1} for {2}'
    message = message.format(wrong, correct, name)

    # Log the error into the Events table
    LogEvent.objects.create(
        test   = test,
        data   = message,
        author = user.username)

    return HttpResponse('None')

@csrf_exempt
@not_minified_response
def clientSubmitNPS(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  POST : Report the speed of the engines in the currently running Test   #
    #         for the User and his Machine. We save this value to display     #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    # Verify the User's credentials
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # Verify the Machine belongs to the User
    machine = Machine.objects.get(id=int(request.POST['machineid']))
    if machine.user != user: return HttpResponse('Bad Machine')

    # Update the NPS and return 'None' to signal no errors
    machine.mnps = float(request.POST['nps']) / 1e6; machine.save()
    return HttpResponse('None')

@csrf_exempt
@not_minified_response
def clientSubmitError(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  POST : Report en Engine error to the server. This could be a crash, a  #
    #         timeloss, a disconnect, or an illegal move. Log the Error into  #
    #         the Events table.                                                #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    # Verify the User's credentials
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # Verify the Machine belongs to the User
    machine = Machine.objects.get(id=int(request.POST['machineid']))
    if machine.user != user: return HttpResponse('Bad Machine')

    # Flag the Test as having an error
    test = Test.objects.get(id=int(request.POST['testid']))
    test.error = True; test.save()

    # Log the Error into the Events table
    LogEvent.objects.create(
        test   = test,
        author = user.username,
        data   = request.POST['error'])

    return HttpResponse('None')

@csrf_exempt
@not_minified_response
def clientSubmitResults(request):

    # Verify the User's credentials
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # Verify the Machine belongs to the User
    machine = Machine.objects.get(id=int(request.POST['machineid']))
    if machine.user != user: return HttpResponse('Bad Machine')

    # updateTest() will return 'None' or 'Stop'
    return HttpResponse(OpenBench.utils.updateTest(request, user))