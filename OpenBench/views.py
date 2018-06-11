from django.shortcuts import render as djangoRender
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate
from django.contrib.auth import login as loginUser
from django.contrib.auth import logout as logoutUser
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required

from OpenBench.config import *
from OpenBench.models import LogEvent, Engine, Profile
from OpenBench.models import Machine, Results, Test

import OpenBench.utils

# Wrap django.shortcuts.render to add framework settings
def render(request, template, data):
    data.update(FRAMEWORK_DEFAULTS)
    return djangoRender(request, 'OpenBench/{0}'.format(template), data)

def register(request):

    # User trying to view the registration page
    if request.method == 'GET':
        return render(request, 'register.html', {})

    try:
        # Attempt to create and login the new user
        user = User.objects.create_user(
            request.POST['username'],
            request.POST['email'],
            request.POST['password']
        )

        # Login the user and return to index
        user.save()
        loginUser(request, user)

        # Wrap the User in a Profile
        profile = Profile()
        profile.user = user
        profile.save()

        # Log the registration
        event = LogEvent()
        event.data = 'Created an account'
        event.author = request.POST['username']
        event.save()

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
        user = authenticate(username=request.POST['username'], password=request.POST['password'])
        loginUser(request, user)
        return HttpResponseRedirect('/index/')

    # Bad data, kick back to index with error
    except Exception as error:
        return index(request, error=str(error))

def logout(request):

    # Logout the user and return to index
    logoutUser(request)
    return HttpResponseRedirect('/index/')

def viewProfile(request):
    pass

def viewUser(request, username):
    return index(request, username=username)

def index(request, page=0, username=None, error=''):

    # Get tests pending approval
    pending = Test.objects.filter(approved=False)
    pending = pending.exclude(deleted=True)
    pending = pending.order_by('-creation')

    # Get tests currently running
    active = Test.objects.filter(approved=True)
    active = active.exclude(finished=True)
    active = active.exclude(deleted=True)
    active = active.order_by('-priority', '-currentllr')

    # Get the complted tests (sliced later)
    completed = Test.objects.filter(finished=True)
    completed = completed.exclude(deleted=True)
    completed = completed.order_by('-completion')

    if username != None: # View from just one user
        pending   = pending.filter(author=username)
        active    = active.filter(author=username)
        completed = completed.filter(author=username)

    # Compile context dictionary
    data = {
        'pending'   : pending,
        'active'    : active,
        'completed' : completed[:50],
        'error'     : error,
    }

    return render(request, 'index.html', data)

def users(request):

    # Build context dictionary for template
    profiles = Profile.objects.all()
    data = {'profiles' : Profile.objects.all()}
    return render(request, 'users.html', data)

def machines(request):
    pass

def eventLog(request):

    # Build context dictionary for template
    data = {'events': LogEvent.objects.all().order_by('-id')[:50]}
    return render(request, 'eventLog.html', data)

@login_required(login_url='/login/')
def newTest(request):

    # User trying to view the new test page
    if request.method == 'GET':
        return render(request, 'newTest.html', {"user" : request.user})

    try:
        # Throw out non-approved / disabled users
        profile = Profile.objects.get(user=request.user)
        if not profile.enabled:
            raise Exception("Account not Enabled")

        # Create test and verify fields
        test = OpenBench.utils.newTest(request)

        # Log the test creation
        event = LogEvent()
        event.data = 'Created test {0} ({1})'.format(str(test), test.id)
        event.author = request.user.username
        event.save()

        return HttpResponseRedirect('/index/')

    # Bad data, kick back to index with error
    except Exception as error:
        return index(request, error=str(error))

def viewTest(request, id):

    try:
        # Find Test and Results
        test = Test.objects.get(id=id)
        results = Results.objects.all().filter(test=test)
        data = {'test' : test, 'results' : results}
        return render(request, 'viewTest.html', data)

    # Unable to find test
    except Exception as error:
        return index(request, error=str(error))

@login_required(login_url='/login/')
def editTest(request, id):

    try:
        # Only let approvers or the author edit a test
        test = Test.objects.get(id=id)
        profile = Profile.objects.get(user=request.user)
        if not profile.approver and test.author != profile.user.username:
            raise Exception("Only Admins Or Test Owners Can Edit A Test")

        # Edit the provided test
        test = Test.objects.get(id=id)
        test.priority = int(request.POST['priority'])
        test.throughput = max(0, int(request.POST['throughput']))
        test.save()

        # Log the test stopping
        event = LogEvent()
        event.data = 'Edit test {0} ({1}) P={2} TP={3}'.format(str(test), test.id, test.priority, test.throughput)
        event.author = request.user.username
        event.save()

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
            raise Exception("No Approver Permissions on Account")

        # Approve the provided test
        test = Test.objects.get(id=id)
        test.approved = True
        test.save()

        # Log the test approval
        event = LogEvent()
        event.data = 'Approved test {0} ({1})'.format(str(test), test.id)
        event.author = request.user.username
        event.save()

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
            raise Exception("Only Admins Or Test Owners Can Restart A Test")

        # Restart the provided test
        test = Test.objects.get(id=id)
        if test.passed or test.failed:
            raise Exception("Test Already Finished via SPRT")
        test.finished = False
        test.save()

        # Log the test stopping
        event = LogEvent()
        event.data = 'Restart test {0} ({1})'.format(str(test), test.id)
        event.author = request.user.username
        event.save()

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
            raise Exception("Only Admins Or Test Owners Can Stop A Test")

        # Stop the provided test
        test = Test.objects.get(id=id)
        test.finished = True
        test.save()

        # Log the test stopping
        event = LogEvent()
        event.data = 'Stopped test {0} ({1})'.format(str(test), test.id)
        event.author = request.user.username
        event.save()

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
            raise Exception("Only Admins Or Test Owners Can Delete A Test")

        # Delete the provided test
        test = Test.objects.get(id=id)
        test.delete = True
        test.save()

        # Log the test deltion
        event = LogEvent()
        event.data = 'Deleted test {0} ({1})'.format(str(test), test.id)
        event.author = request.user.username
        event.save()

        return HttpResponseRedirect('/index/')

    # Bad test id, permissions, or other
    except Exception as error:
        return index(request, error=str(error))


def getFiles(request):
    pass

def getWorkload(request):
    pass

def submitResults(request):
    pass

def invalidBench(request):
    pass