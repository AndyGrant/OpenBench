from django.shortcuts import render as djangoRender

# Wrap django.shortcuts.render to add framework settings
def render(request, template, data):
    data.update(FRAMEWORK_DEFAULTS)
    return djangoRender(request, 'OpenBench/{0}'.format(template), data)

## ADMIN

def register(request):
    pass

def login(request):
    pass

def logout(request):
    pass

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