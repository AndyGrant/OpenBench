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

import django.http
import django.shortcuts
import django.contrib.auth

import OpenBench.config
import OpenBench.utils

from OpenBench.models import *
from django.contrib.auth.models import User

from django.db.models import F
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from htmlmin.decorators import not_minified_response

def render(request, template, data={}):

    template = 'OpenBench/{0}'.format(template)

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
    #  POST : Logout the User if they are logged in. Return to the main page  #
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
    #  POST : Return all pending, active, and completed tests. Limit the      #
    #         display of tests by the requested page number. Also display the #
    #         status for connected machines.                                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    pending   = OpenBench.utils.getPendingTests()
    active    = OpenBench.utils.getActiveTests()
    completed = OpenBench.utils.getCompletedTests()

    completed, paging = OpenBench.utils.getPaging(completed, page, 'index')

    data = {
        'error'  : error,  'pending'   : pending,
        'active' : active, 'completed' : completed,
        'paging' : paging, 'status'    : OpenBench.utils.getMachineStatus(),
    }

    return render(request, 'index.html', data)

def greens(request, page=1):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return all tests both passed and completed. Limit the display   #
    #         of tests by the requested page number.                          #
    #                                                                         #
    #  POST : Return all tests both passed and completed. Limit the display   #
    #         of tests by the requested page number.                          #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    completed = OpenBench.utils.getCompletedTests().filter(passed=True)
    completed, paging = OpenBench.utils.getPaging(completed, page, 'greens')

    data = {'completed' : completed, 'paging' : paging}
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

    tests = Test.objects.all().order_by('-updated')

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

    keywords = ['(?i)' + f.upper() for f in request.POST['keywords'].split()]
    tests = tests.filter(dev__name__regex=r'{0}'.format('|'.join(keywords)))
    return render(request, 'search.html', {'tests' : tests})

def user(request, username, page=1):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return all pending, active, and completed tests for the User    #
    #         that has been requested. Limit the display of completed tests   #
    #         by the requested page number. Also display the User's machines  #
    #                                                                         #
    #  POST : Return all pending, active, and completed tests for the User    #
    #         that has been requested. Limit the display of completed tests   #
    #         by the requested page number. Also display the User's machines  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    pending   = OpenBench.utils.getPendingTests().filter(author=username)
    active    = OpenBench.utils.getActiveTests().filter(author=username)
    completed = OpenBench.utils.getCompletedTests().filter(author=username)

    url = 'user/{0}'.format(username)
    completed, paging = OpenBench.utils.getPaging(completed, page, url)

    data = {
        'pending'   : pending,   'active' : active,
        'completed' : completed, 'paging' : paging,
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
    #  POST : Return information about all users on the Framework. Sort the   #
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
    #  POST : Return information about the events taken on the Framework.     #
    #         Only show those events for the requested page.                  #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    events = LogEvent.objects.all().order_by('-id')
    events, paging = OpenBench.utils.getPaging(events, page, 'events')

    data = {'events' : events, 'paging' : paging};
    return render(request, 'events.html', data)

def machines(request):

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #                                                                         #
    #  GET  : Return information about all of the machines that have been     #
    #         active on the Framework within the last fifteen minutes         #
    #                                                                         #
    #  POST : Return information about all of the machines that have been     #
    #         active on the Framework within the last fifteen minutes         #
    #                                                                         #
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

    data = {'machines' : OpenBench.utils.getRecentMachines()}
    return render(request, 'machines.html', data)


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
    #         errors is prestented back to the User on the homepage           #
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
    LogEvent.objects.create(data="CREATE", author=username, test=test)
    return django.http.HttpResponseRedirect('/index/')


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                              CLIENT HOOK VIEWS                              #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

@csrf_exempt
@not_minified_response
def getFiles(request):

    # Core Files should be sitting in framework's repo
    return HttpResponse(OpenBench.config.OPENBENCH_CONFIG['corefiles'])

@csrf_exempt
@not_minified_response
def getWorkload(request):

    # Verify that we got a valid login
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # Create or fetch the Machine
    try: machine = OpenBench.utils.getMachine(
            request.POST['machineid'],
            request.POST['username'],
            request.POST['osname'],
            request.POST['threads'])
    except: return HttpResponse('Bad Machine')

    # Find an active Test to work on
    try:
        test = OpenBench.utils.getWorkload(machine)
        machine.workload = test
        machine.save()
    except:
        return HttpResponse('None')

    # Create or fetch the Results
    try: result = OpenBench.utils.getResult(machine, test)
    except: return HttpResponse('None')

    # Send ID's and test information as a string dictionary
    return HttpResponse(str(OpenBench.utils.workloadDictionary(machine, result, test)))

@csrf_exempt
@not_minified_response
def wrongBench(request):

    # Verify that we got a valid login
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    try:
        # Find the engine with the bad bench
        engineid = int(request.POST['engineid'])
        engine = Engine.objects.get(id=engineid)

        # Find and stop the test with the bad bench
        testid = int(request.POST['testid'])
        test = Test.objects.get(id=testid)
        test.finished = True
        test.save()

        # Log the bad bench so we know why the test was stopped
        LogEvent.objects.create(
            data='Invalid Bench',
            author=request.POST['username'],
            test=test)
    except: pass

    return HttpResponse('None')

@csrf_exempt
@not_minified_response
def submitNPS(request):

    # Verify that we got a valid login
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Bad Credentials')

    # Try to update the NPS for the machine
    try:
        machine = Machine.objects.get(id=int(request.POST['machineid']))
        machine.mnps = float(request.POST['nps']) / 1e6
        machine.save()
    except: return HttpResponse('Bad Machine ID')

    return HttpResponse('None')

@csrf_exempt
@not_minified_response
def submitResults(request):

    # Verify that we got a valid login
    user = django.contrib.auth.authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Stop')

    # Try to update each location
    try: OpenBench.utils.update(request, user)
    except: return HttpResponse('Stop')

    return HttpResponse('None')