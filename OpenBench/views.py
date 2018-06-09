from django.shortcuts import render as djangoRender

from django.http import HttpResponse, HttpResponseRedirect

from django.contrib.auth import authenticate
from django.contrib.auth import login as loginUser
from django.contrib.auth import logout as logoutUser
from django.contrib.auth.models import User

from OpenBench.config import *

from OpenBench.models import LogEvent, Engine, Profile
from OpenBench.models import Machine, Results, Test

# Wrap django.shortcuts.render to add framework settings
def render(request, template, data):
    data.update(FRAMEWORK_DEFAULTS)
    return djangoRender(request, 'OpenBench/{0}'.format(template), data)

def register(request):

    # User trying to view the registration page
    if request.method == 'GET':
        return render(request, 'register.html', {})

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
    event.data = 'Created user {0}'.format(request.POST['username'])
    event.save()

    return HttpResponseRedirect('/index/')

def login(request):

    # User trying to view the login page
    if request.method == 'GET':
        return render(request, 'login.html', {})

    # Attempt to login the user, and return to index
    user = authenticate(username=request.POST['username'], password=request.POST['password'])
    loginUser(request, user)
    return HttpResponseRedirect('/index/')

def logout(request):

    # Logout the user and return to index
    logoutUser(request)
    return HttpResponseRedirect('/index/')

def index(request, page=0):

    # Get tests pending approval
    pending = Test.objects.filter(approved=False)
    pending = pending.exclude(deleted=True)
    pending = pending.order_by('creation')

    # Get tests currently running
    active = Test.objects.filter(approved=True)
    active = active.exclude(passed=True)
    active = active.exclude(failed=True)
    active = active.exclude(deleted=True)
    active = active.order_by('priority', 'currentllr')

    # Get the last 50 completed tests
    completed = Test.objects.filter(finished=True)
    completed = completed.exclude(deleted=True)
    completed = completed.order_by('completion')

    # Get machines currently active workloads
    # machines = Machine.objects.get()
    # machines = Machines played within last <minutes>
    # Save my @nitrocan @defenchess

    data = {
        'pending'   : pending,
        'active'    : active,
        'completed' : completed,
    }

    return render(request, 'index.html', data)

def users(request):
    profiles = Profile.objects.all()
    data = {'profiles' : Profile.objects.all()}
    return render(request, 'users.html', data)

def machines(request):
    pass

def eventLog(request):

    # Build context dictionary for template
    data = {'events': []}
    for event in LogEvent.objects.all():
        data['events'].append({
            'data'     : event.data,
            'creation' : event.creation})

    return render(request, 'eventLog.html', data)

def newTest(request):
    pass

def editTest(request, id):
    pass

def viewTest(request, id):
    pass

def approveTest(request, id):
    pass

def getFiles(request):
    pass

def getWorkload(request):
    pass

def submitResults(request):
    pass

def invalidBench(request):
    pass