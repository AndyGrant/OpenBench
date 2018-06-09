from django.contrib import admin
from django.urls import path, include

import OpenBench.urls

urlpatterns = [
    path(r'admin/', admin.site.urls),
    path(r'^', include(OpenBench.urls.urlpatterns)),
]
