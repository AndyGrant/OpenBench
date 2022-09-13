# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                             #
#   OpenBench is a chess engine testing framework authored by Andrew Grant.   #
#   <https://github.com/AndyGrant/OpenBench>           <andrew@grantnet.us>   #
#                                                                             #
#   OpenBench is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU General Public License as published by      #
#   the Free Software Foundation, either version 3 of the License, or         #
#   (at your option) any later version.                                       #
#                                                                             #
#   OpenBench is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#   GNU General Public License for more details.                              #
#                                                                             #
#   You should have received a copy of the GNU General Public License         #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import django.urls, OpenBench.views

urlpatterns = [

    # Links for account managment
    django.urls.path(r'register/', OpenBench.views.register),
    django.urls.path(r'login/', OpenBench.views.login),
    django.urls.path(r'logout/', OpenBench.views.logout),
    django.urls.path(r'profile/', OpenBench.views.profile),

    # Links for viewing test tables
    django.urls.path(r'index/', OpenBench.views.index),
    django.urls.path(r'index/<int:page>/', OpenBench.views.index),
    django.urls.path(r'greens/', OpenBench.views.greens),
    django.urls.path(r'greens/<int:page>/', OpenBench.views.greens),
    django.urls.path(r'search/', OpenBench.views.search),
    django.urls.path(r'user/<str:username>/', OpenBench.views.user),
    django.urls.path(r'user/<str:username>/<int:page>/', OpenBench.views.user),
    django.urls.path(r'event/<int:id>/', OpenBench.views.event),

    # Links for viewing general information tables
    django.urls.path(r'users/', OpenBench.views.users),
    django.urls.path(r'events/', OpenBench.views.events),
    django.urls.path(r'events/<int:page>/', OpenBench.views.events),
    django.urls.path(r'machines/', OpenBench.views.machines),

    # Links for viewing and managing tests (maintain Legacy)
    django.urls.path(r'test/<int:id>/', OpenBench.views.test),
    django.urls.path(r'viewTest/<int:id>/', OpenBench.views.test),
    django.urls.path(r'test/<int:id>/<str:action>', OpenBench.views.test),
    django.urls.path(r'newTest/', OpenBench.views.newTest),

    # Links for viewing and managing Networks
    django.urls.path(r'networks/', OpenBench.views.networks),
    django.urls.path(r'networks/<str:action>/', OpenBench.views.networks),
    django.urls.path(r'networks/<str:action>/<str:sha256>/', OpenBench.views.networks),

    # Links for interacting with OpenBench via scripting
    django.urls.path(r'scripts/', OpenBench.views.scripts),

    # Links for the Client to work with the Server
    django.urls.path(r'clientGetFiles/', OpenBench.views.clientGetFiles),
    django.urls.path(r'clientGetBuildInfo/', OpenBench.views.clientGetBuildInfo),
    django.urls.path(r'clientGetWorkload/', OpenBench.views.clientGetWorkload),
    django.urls.path(r'clientGetNetwork/<str:sha256>/', OpenBench.views.clientGetNetwork),
    django.urls.path(r'clientWrongBench/', OpenBench.views.clientWrongBench),
    django.urls.path(r'clientSubmitNPS/', OpenBench.views.clientSubmitNPS),
    django.urls.path(r'clientSubmitError/', OpenBench.views.clientSubmitError),
    django.urls.path(r'clientSubmitResults/', OpenBench.views.clientSubmitResults),

    # Redirect anything else to the Index
    django.urls.path(r'', OpenBench.views.index),

    # Link for Ethereal 13.00 PRO Sales
    django.urls.path(r'Ethereal/', OpenBench.views.buyEthereal),
]
