from django.urls import path

import OpenBench.views

urlpatterns = [
    path(r'register/', OpenBench.views.register),
    path(r'login/', OpenBench.views.login),
    path(r'logout/', OpenBench.views.logout),

    path(r'index/', OpenBench.views.index),
    path(r'index/<int:page>/', OpenBench.views.index),
    path(r'users/', OpenBench.views.users),
    path(r'machines/', OpenBench.views.machines),
    path(r'eventLog/', OpenBench.views.eventLog),

    path(r'newTest/', OpenBench.views.newTest),
    path(r'editTest/<int:id>/', OpenBench.views.editTest),
    path(r'viewTest/<int:id>/', OpenBench.views.viewTest),
    path(r'approveTest/<int:id>/', OpenBench.views.approveTest),

    path(r'getFiles/', OpenBench.views.getFiles),
    path(r'getWorkload/', OpenBench.views.getFiles),
    path(r'submitResults/', OpenBench.views.submitResults),
    path(r'invalidBench/', OpenBench.views.invalidBench),
]
