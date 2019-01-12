from django.db.models import F
from django.shortcuts import render as djangoRender
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate
from django.contrib.auth import login as loginUser
from django.contrib.auth import logout as logoutUser
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import utc

from OpenBench.config import *
from OpenBench.models import LogEvent, Engine, Profile
from OpenBench.models import Machine, Result, Test
from OpenBench.utils import pagingContext

import OpenBench.utils, datetime


# Wrap django.shortcuts.render to add framework settings
def render(request, template, data):
    data.update(FRAMEWORK_DEFAULTS)
    return djangoRender(request, 'OpenBench/{0}'.format(template), data)

def register(request):

    # User trying to view the registration page
    if request.method == 'GET':
        return render(request, 'register.html', {})

    try:
        # Verify that the passwords are matching
        if request.POST['password1'] != request.POST['password2']:
            raise Exception('Passwords Do Not Match')

        # Force alpha numeric usernames
        if not request.POST['username'].isalnum():
            raise Exception('Alpha Numeric Usernames Only')

        # Create new User and Profile
        Profile.objects.create(
            user=User.objects.create_user(
                request.POST['username'],
                request.POST['email'],
                request.POST['password1']))

        # Log the User in now
        loginUser(request, User.objects.get(username=request.POST['username']))

        # Kick back to index
        return HttpResponseRedirect('/index/')

    # Bad data, kick back to index with error
    except Exception as error:
        return index(request, error=str(error))

def login(request):

    # User trying to view the login page
    if request.method == 'GET':
        return render(request, 'login.html', {})

    try:
        # Attempt to login the user, and return to index
        loginUser(request, authenticate(
            username=request.POST['username'],
            password=request.POST['password']))
        return HttpResponseRedirect('/index/')

    # Bad data, kick back to index with error
    except Exception as error:
        return index(request, error='Invalid Login Credentials')

def logout(request):

    # Logout the user and return to index
    logoutUser(request)
    return HttpResponseRedirect('/index/')

@login_required(login_url='/login/')
def viewProfile(request):

    # Build context dictionary for profile template
    profile = Profile.objects.get(user=request.user)
    data = {'profile' : profile}
    return render(request, 'viewProfile.html', data)

@login_required(login_url='/login/')
def editProfile(request):

    # Update Email & Source Repo
    profile = Profile.objects.get(user=request.user)
    profile.user.email = request.POST['email']
    profile.repo = request.POST['repo']
    profile.save()

    # Change Passwords
    password1 = request.POST['password1']
    password2 = request.POST['password2']
    if password1 != '' and password1 == password2:
        profile.user.set_password(password1)
        profile.user.save()
        loginUser(request, authenticate(
            username=request.user.username,
            password=password1))

    # Send back to see the changes
    return HttpResponseRedirect('/viewProfile/')

def index(request, page=0, pageLength=25, greens=False, username=None, error=''):

    # Get tests pending approval
    pending = Test.objects.filter(approved=False)
    pending = pending.exclude(finished=True)
    pending = pending.exclude(deleted=True)
    pending = pending.order_by('-creation')

    # Get tests currently running
    active = Test.objects.filter(approved=True)
    active = active.exclude(finished=True)
    active = active.exclude(deleted=True)
    active = active.order_by('-priority', '-currentllr')

    # Get the completed tests (sliced later)
    completed = Test.objects.filter(finished=True)
    completed = completed.exclude(deleted=True)
    completed = completed.order_by('-updated')

    # Pull data from active machines
    target   = datetime.datetime.utcnow().replace(tzinfo=utc) - datetime.timedelta(minutes=10)
    machines = Machine.objects.filter(updated__gte=target)
    if username != None: machines = machines.filter(owner=username)

    # Extract stat information from workers
    machineCount = len(machines)
    threadCount  = sum(machine.threads for machine in machines)
    npsTotal     = sum(machine.threads * machine.mnps for machine in machines)
    workerData   = "{0} Machines {1} Threads {2} MNPS".format(
        machineCount, threadCount, round(npsTotal, 2)
    )

    # Index is wrapped for just viewing passed tests
    if greens == True:
        pending   = active = []
        completed = completed.filter(passed=True)
        source    = 'greens'

    # Index is wrapped just to view one user
    elif username != None:
        pending   = pending.filter(author=username)
        active    = active.filter(author=username)
        completed = completed.filter(author=username)
        source    = "viewUser/{0}".format(username)

    # Index is normal, not wrapped for any views
    else:
        source    = "index"

    # Choose tests within the given page, if any
    items  = len(completed)
    start  = page * pageLength
    end    = start + pageLength
    start  = max(0, min(start, items))
    end    = max(0, min(end, items))
    paging = pagingContext(page, pageLength, items, source)

    # Build context dictionary for index template
    data = {
        'error'     : error,
        'pending'   : pending,
        'active'    : active,
        'completed' : completed[start:end],
        'status'    : workerData,
        'greens'    : greens,
        'paging'    : paging,
    }

    return render(request, 'index.html', data)

def greens(request, page=0):

    # Index but with only passed tests
    return index(request, page, greens=True)

def search(request):

    # First time viewing the page
    if request.method == 'GET':
        return render(request, 'search.html', {'tests' : []})

    # Base starting point with all tests
    tests = Test.objects.all()

    # Only show tests for selected engine (default is all engines)
    if request.POST['engine'] != '':
        tests = tests.filter(engine=request.POST['engine'])

    # Only show tests from a selected author (default is all authors)
    if request.POST['author'] != '':
        tests = tests.filter(author=request.POST['author'])

    # Don't show tests that have passed
    if request.POST['showgreens'] == 'False':
        tests = tests.exclude(passed=True)

    # Don't show tests that have failed yellow
    if request.POST['showyellows'] == 'False':
        tests = tests.exclude(failed=True,wins__gte=F('losses'))

    # Don't show tests that have failed red
    if request.POST['showreds']  == 'False':
        tests = tests.exclude(failed=True,wins__lt=F('losses'))

    # Don't show tests that are unfinished
    if request.POST['showunfinished'] == 'False':
        tests = tests.exclude(passed=False,failed=False)

    # Don't show tests that have been deleted
    if request.POST['showdeleted'] == 'False':
        tests = tests.exclude(deleted=True)

    # If there are no keywords, we are done searching
    keywords = request.POST['keywords'].split()
    if keywords == []:
        return render(request, 'search.html', {'tests' : tests.order_by('-updated')})

    # Only grab tests which contain at least one keyword
    filtered = []
    for test in tests.order_by('-updated'):
        for keyword in keywords:
            if keyword.upper() in test.dev.name.upper():
                filtered.append(test)
                break
    return render(request, 'search.html', {'tests' : filtered})

def viewUser(request, username, page=0):

    # Index but with only username's tests
    return index(request, page, username=username)

def users(request):

    # Build context dictionary for template
    data = {'profiles' : Profile.objects.order_by('-games')}
    return render(request, 'users.html', data)

def machines(request):

    # Build context dictionary for machine template with machines updated recently
    target = datetime.datetime.utcnow().replace(tzinfo=utc) - datetime.timedelta(minutes=10)
    data = {'machines' : Machine.objects.filter(updated__gte=target)}
    return render(request, 'machines.html', data)

def eventLog(request, page=0, pageLength=50):

    # Choose events within the given page, if any
    events = LogEvent.objects.all().order_by('-id')
    items  = len(events)
    start  = page * pageLength
    end    = start + pageLength
    start  = max(0, min(start, items))
    end    = max(0, min(end, items))
    paging = pagingContext(page, pageLength, items, 'eventLog')

    # Build context dictionary for event log template
    data = {
        'events': events[start:end],
        'paging': paging
    }

    return render(request, 'eventLog.html', data)

@login_required(login_url='/login/')
def newTest(request):

    # User trying to view the new test page
    if request.method == 'GET':
        profile = Profile.objects.get(user=request.user)
        return render(request, 'newTest.html', {'profile' : profile})

    try:
        # Throw out non-approved / disabled users
        if not Profile.objects.get(user=request.user).enabled:
            raise Exception('Account not Enabled')

        # Create test and verify fields
        test = OpenBench.utils.newTest(request)

        # Log the test creation
        LogEvent.objects.create(
            data='Created Test',
            author=request.user.username,
            test=test)

        return HttpResponseRedirect('/index/')

    # Bad data, kick back to index with error
    except Exception as error:
        return index(request, error=str(error))

def viewTest(request, id):

    try:
        # Build context dictionary for test template
        test = Test.objects.get(id=id)
        results = Result.objects.all().filter(test=test)
        data = {'test' : test, 'results' : results}
        return render(request, 'viewTest.html', data)

    # Unable to find test
    except Exception as error:
        return index(request, error=str(error))

@login_required(login_url='/login/')
def editTest(request, id):

    try:
        # Only let approvers or the test author edit a test
        test = Test.objects.get(id=id)
        profile = Profile.objects.get(user=request.user)
        if not profile.approver and test.author != profile.user.username:
            raise Exception('Only Admins Or Test Owners Can Edit A Test')

        # Edit the provided test
        test = Test.objects.get(id=id)
        test.priority = int(request.POST['priority'])
        test.throughput = max(0, int(request.POST['throughput']))
        test.save()

        # Log changes to the test settings
        LogEvent.objects.create(
            data='Edited Test P={0} TP={1}'.format(test.priority, test.throughput),
            author=request.user.username,
            test=test)

        return HttpResponseRedirect('/index/')

    # Bad test id, permissions, or other
    except Exception as error:
        return index(request, error=str(error))

@login_required(login_url='/login/')
def approveTest(request, id):

    try:
        # Throw out users without approver status
        profile = Profile.objects.get(user=request.user)
        if not profile.approver:
            raise Exception('No Approver Permissions on Account')

        # Approve the provided test
        test = Test.objects.get(id=id)
        if test.approved:
            return HttpResponseRedirect('/index/')
        test.approved = True
        test.save()

        # Log the test approval
        LogEvent.objects.create(
            data='Approved Test',
            author=request.user.username,
            test=test)

        return HttpResponseRedirect('/index/')

    # Bad test id, permissions, or other
    except Exception as error:
        return index(request, error=str(error))

@login_required(login_url='/login/')
def restartTest(request, id):

    try:
        # Only let approvers or the author restart a test
        test = Test.objects.get(id=id)
        profile = Profile.objects.get(user=request.user)
        if not profile.approver and test.author != profile.user.username:
            raise Exception('Only Admins Or Test Owners Can Restart A Test')

        # Restart the provided test
        test = Test.objects.get(id=id)
        if not test.finished:
            return HttpResponseRedirect('/index/')
        test.finished = False
        test.save()

        # Log the test stopping
        LogEvent.objects.create(
            data='Restarted Test',
            author=request.user.username,
            test=test)

        return HttpResponseRedirect('/index/')

    # Bad test id, permissions, or other
    except Exception as error:
        return index(request, error=str(error))

@login_required(login_url='/login/')
def stopTest(request, id):

    try:
        # Only let approvers or the author stop a test
        test = Test.objects.get(id=id)
        profile = Profile.objects.get(user=request.user)
        if not profile.approver and test.author != profile.user.username:
            raise Exception('Only Admins Or Test Owners Can Stop A Test')

        # Stop the provided test
        test = Test.objects.get(id=id)
        if test.finished:
            return HttpResponseRedirect('/index/')
        test.finished = True
        test.save()

        # Log the test stopping
        LogEvent.objects.create(
            data='Stopped Test',
            author=request.user.username,
            test=test)

        return HttpResponseRedirect('/index/')

    # Bad test id, permissions, or other
    except Exception as error:
        return index(request, error=str(error))

@login_required(login_url='/login/')
def deleteTest(request, id):

    try:
        # Only let approvers or the author delete a test
        test = Test.objects.get(id=id)
        profile = Profile.objects.get(user=request.user)
        if not profile.approver and test.author != profile.user.username:
            raise Exception('Only Admins Or Test Owners Can Delete A Test')

        # Delete the provided test
        test = Test.objects.get(id=id)
        if test.deleted:
            return HttpResponseRedirect('/index/')
        test.deleted = True
        test.save()

        # Reduce the test count for the test author
        user = User.objects.get(username=test.author)
        profile = Profile.objects.get(user=user)
        profile.tests -= 1
        profile.save()

        # Log the test deltion
        LogEvent.objects.create(
            data='Deleted Test',
            author=request.user.username,
            test=test)

        return HttpResponseRedirect('/index/')

    # Bad test id, permissions, or other
    except Exception as error:
        return index(request, error=str(error))

@csrf_exempt
def getFiles(request):

    # Core Files should be sitting in framework's repo
    source = FRAMEWORK_REPO_URL + 'raw/master/CoreFiles/'
    return HttpResponse(source)

@csrf_exempt
def getWorkload(request):

    # Verify that we got a valid login
    user = authenticate(
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
def wrongBench(request):

    # Verify that we got a valid login
    user = authenticate(
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
def submitNPS(request):

    # Verify that we got a valid login
    user = authenticate(
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
def submitResults(request):

    # Verify that we got a valid login
    user = authenticate(
        username=request.POST['username'],
        password=request.POST['password'])
    if user == None: return HttpResponse('Stop')

    # Try to update each location
    try: OpenBench.utils.update(request, user)
    except: return HttpResponse('Stop')

    return HttpResponse('None')