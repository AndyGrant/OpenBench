from django.urls import path

import OpenBench.views

urlpatterns = [
    path(r'register/', OpenBench.views.register),
    path(r'login/', OpenBench.views.login),
    path(r'logout/', OpenBench.views.logout),

    path(r'viewProfile/', OpenBench.views.viewProfile),
    path(r'editProfile/', OpenBench.views.editProfile),

    path(r'index/', OpenBench.views.index),
    path(r'index/<int:page>/', OpenBench.views.index),
    path(r'users/', OpenBench.views.users),
    path(r'viewUser/<str:username>/', OpenBench.views.viewUser),
    path(r'machines/', OpenBench.views.machines),
    path(r'eventLog/', OpenBench.views.eventLog),

    path(r'newTest/', OpenBench.views.newTest),
    path(r'viewTest/<int:id>/', OpenBench.views.viewTest),
    path(r'editTest/<int:id>/', OpenBench.views.editTest),
    path(r'approveTest/<int:id>/', OpenBench.views.approveTest),
    path(r'restartTest/<int:id>/', OpenBench.views.restartTest),
    path(r'stopTest/<int:id>/', OpenBench.views.stopTest),
    path(r'deleteTest/<int:id>/', OpenBench.views.deleteTest),

    path(r'getFiles/', OpenBench.views.getFiles),
    path(r'getWorkload/', OpenBench.views.getWorkload),
    path(r'submitResults/', OpenBench.views.submitResults),
    path(r'invalidBench/', OpenBench.views.invalidBench),
]
