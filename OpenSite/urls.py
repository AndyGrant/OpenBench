from django.contrib import admin
from django.urls import path, include
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

import OpenBench.urls

urlpatterns = [
    path(r'admin/', admin.site.urls),
    path(r'', include(OpenBench.urls.urlpatterns)),
]

urlpatterns += staticfiles_urlpatterns()