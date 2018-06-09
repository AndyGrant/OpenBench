from django.conf.urls import url

import OpenBench.views

urlpatterns = [
    path(r'register/$', OpenBench.views.register),
    path(r'login/$', OpenBench.views.login),
    path(r'logout/$', OpenBench.views.logout),

    path(r'log/$', OpenBench.views.log),
    path(r'index/([0-9]+)/$', OpenBench.views.index),
    path(r'greens/([0-9]+)/$', OpenBench.views.greens),

    path(r'newTest/$', OpenBench.views.newTest),
    path(r'editTest/([0-9]+)/$', OpenBench.views.editTest),
    path(r'viewTest/([0-9]+)/$', OpenBench.views.viewTest),
    path(r'approveTest/([0-9]+)/$', OpenBench.views.approveTest),

    path(r'getFiles/$', OpenBench.views.getFiles),
    path(r'getWorkload/$', OpenBench.views.getFiles),
    path(r'submitResults/$', OpenBench.views.submitResults),
    path(r'invalidBench/$', OpenBench.views.invalidBench),
]
