from django.shortcuts import render as djangoRender

from django.http import HttpResponse, HttpResponseRedirect

from django.contrib.auth import authenticate
from django.contrib.auth import login as loginUser
from django.contrib.auth import logout as logoutUser
from django.contrib.auth.models import User



from OpenBench.config import *

# Wrap django.shortcuts.render to add framework settings
def render(request, template, data):
    data.update(FRAMEWORK_DEFAULTS)
    return djangoRender(request, 'OpenBench/{0}'.format(template), data)

## ADMIN

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
    return HttpResponseRedirect("/index/")

def login(request):

    # User trying to view the login page
    if request.method == "GET":
        return render(request, "login.html", {})

    # Attempt to login the user, and return to index
    user = authenticate(username=request.POST["username"], password=request.POST["password"])
    loginUser(request, user)
    return HttpResponseRedirect("/index/")

def logout(request):

    # Logout the user and return to index
    logoutUser(request)
    return HttpResponseRedirect("/index/")

## CONTENT VIEWING

def eventLog(request):
    pass

def index(request, page=0):
    pass

## TEST MANAGMENT

def newTest(request):
    pass

def editTest(request, id):
    pass

def viewTest(request, id):
    pass

def approveTest(request, id):
    pass

## CLIENT TARGETS

def getFiles(request):
    pass

def getWorkload(request):
    pass

def submitResults(request):
    pass

def invalidBench(request):
    pass