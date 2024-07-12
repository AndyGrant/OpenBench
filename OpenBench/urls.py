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

    # Links for account management
    django.urls.path(r'register/', OpenBench.views.register),
    django.urls.path(r'login/', OpenBench.views.login),
    django.urls.path(r'logout/', OpenBench.views.logout),
    django.urls.path(r'profile/', OpenBench.views.profile),
    django.urls.path(r'profileConfig/', OpenBench.views.profile_config),

    # Links for viewing test tables
    django.urls.path(r'index/', OpenBench.views.index),
    django.urls.path(r'index/<int:page>/', OpenBench.views.index),
    django.urls.path(r'user/<str:username>/', OpenBench.views.user),
    django.urls.path(r'user/<str:username>/<int:page>/', OpenBench.views.user),
    django.urls.path(r'greens/', OpenBench.views.greens),
    django.urls.path(r'greens/<int:page>/', OpenBench.views.greens),
    django.urls.path(r'search/', OpenBench.views.search),

    # Links for viewing general information tables
    django.urls.path(r'users/', OpenBench.views.users),
    django.urls.path(r'event/<int:id>/', OpenBench.views.event),
    django.urls.path(r'events/', OpenBench.views.events_actions),
    django.urls.path(r'events/<int:page>/', OpenBench.views.events_actions),
    django.urls.path(r'errors/', OpenBench.views.events_errors),
    django.urls.path(r'errors/<int:page>/', OpenBench.views.events_errors),
    django.urls.path(r'machines/', OpenBench.views.machines),
    django.urls.path(r'machines/<int:machineid>/', OpenBench.views.machines),

    # Links for viewing and managing tests
    django.urls.path(r'test/<int:id>/', OpenBench.views.test),
    django.urls.path(r'test/<int:id>/<str:action>', OpenBench.views.test),
    django.urls.path(r'newTest/', OpenBench.views.create_test),

    # Links for viewing and managing tunes
    django.urls.path(r'tune/<int:id>/', OpenBench.views.tune),
    django.urls.path(r'tune/<int:id>/<str:action>', OpenBench.views.tune),
    django.urls.path(r'newTune/', OpenBench.views.create_tune),

    # Links for viewing and managing datagen
    django.urls.path(r'datagen/<int:id>/', OpenBench.views.datagen),
    django.urls.path(r'datagen/<int:id>/<str:action>', OpenBench.views.datagen),
    django.urls.path(r'newDatagen/', OpenBench.views.create_datagen),

    # Links for viewing and managing Networks
    django.urls.path(r'networks/', OpenBench.views.networks),
    django.urls.path(r'networks/<str:engine>/', OpenBench.views.networks),
    django.urls.path(r'networks/<str:engine>/<str:action>/', OpenBench.views.networks),
    django.urls.path(r'networks/<str:engine>/<str:action>/<str:name>/', OpenBench.views.networks),
    django.urls.path(r'newNetwork/', OpenBench.views.network_form),

    # Links for interacting with OpenBench via scripting
    django.urls.path(r'scripts/', OpenBench.views.scripts),

    # Links for the Client to work with the Server
    django.urls.path(r'clientVersionRef/', OpenBench.views.client_version_ref),
    django.urls.path(r'clientGetBuildInfo/', OpenBench.views.client_get_build_info),
    django.urls.path(r'clientWorkerInfo/', OpenBench.views.client_worker_info),
    django.urls.path(r'clientGetWorkload/', OpenBench.views.client_get_workload),
    django.urls.path(r'clientGetNetwork/<str:engine>/<str:name>/', OpenBench.views.client_get_network),
    django.urls.path(r'clientBenchError/', OpenBench.views.client_bench_error),
    django.urls.path(r'clientSubmitNPS/', OpenBench.views.client_submit_nps),
    django.urls.path(r'clientSubmitError/', OpenBench.views.client_submit_error),
    django.urls.path(r'clientSubmitResults/', OpenBench.views.client_submit_results),
    django.urls.path(r'clientHeartbeat/', OpenBench.views.client_heartbeat),
    django.urls.path(r'clientSubmitPGN/', OpenBench.views.client_submit_pgn),

    # Nice endpoints, which can be hit from the website or with credentials cleanly
    django.urls.path(r'api/config/', OpenBench.views.api_configs),
    django.urls.path(r'api/config/<str:engine>/', OpenBench.views.api_configs),
    django.urls.path(r'api/networks/<str:engine>/', OpenBench.views.api_networks),
    django.urls.path(r'api/networks/<str:engine>/<str:identifier>/', OpenBench.views.api_network_download),
    django.urls.path(r'api/buildinfo/', OpenBench.views.api_build_info),
    django.urls.path(r'api/pgns/<int:pgn_id>/', OpenBench.views.api_pgns),

    # Redirect anything else to the Index
    django.urls.path(r'', OpenBench.views.index),

    # Link for Ethereal Sales
    django.urls.path(r'Ethereal/', OpenBench.views.buyEthereal),
]
