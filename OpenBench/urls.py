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

from django.urls import path, re_path

from OpenBench import views

urlpatterns = [

    # Links for account management
    path(r'register/', views.register),
    path(r'login/', views.login),
    path(r'logout/', views.logout),
    path(r'profile/', views.profile),
    path(r'profileConfig/', views.profile_config),

    # Links for viewing test tables
    re_path(r'^index(?:/(?P<page>\d+))?/$', views.index),
    re_path(r'^user/(?P<username>[^/]+)(?:/(?P<page>\d+))?/$', views.user),
    re_path(r'^greens(?:/(?P<page>\d+))?/$', views.greens),

    path(r'search/', views.search),

    # Links for viewing general information tables
    path(r'users/', views.users),
    path(r'event/<int:pk>/', views.event),
    re_path(r'^events(?:/(?P<page>\d+))?/$', views.events_actions),
    re_path(r'^errors(?:/(?P<page>\d+))?/$', views.events_errors),
    re_path(r'^machines(?:/(?P<pk>\d+))?/$', views.machines),

    # Links to create, view or manage Workloads (Tests, Tunes, Datagen)
    re_path(r'^(?P<workload_type>tune|test|datagen)/new/$', views.new_workload),
    re_path(r'^(?P<workload_type>tune|test|datagen)/(?P<pk>\d+)(?:/(?P<action>\w+))?/$', views.workload),

    # Links for viewing and managing Networks
    path(r'networks/', views.networks),
    path(r'networks/<str:engine>/', views.networks),
    path(r'networks/<str:engine>/<str:action>/', views.networks),
    path(r'networks/<str:engine>/<str:action>/<str:name>/', views.networks),
    path(r'newNetwork/', views.network_form),

    # Links for viewing and managing the Server's configuration
    path(r'manage/', views.manage),
    path(r'manage/books/', views.manage_books),
    path(r'manage/books/<str:name>/', views.manage_books),
    path(r'manage/books/<str:name>/<str:action>/', views.manage_books),

    path(r'manage/engines/', views.manage_engines),
    path(r'manage/engines/<str:name>/', views.manage_engines),
    path(r'manage/engines/<str:name>/<str:action>/', views.manage_engines),

    # Links for interacting with OpenBench via scripting
    path(r'scripts/', views.scripts),

    # Links for the Client to work with the Server
    path(r'clientVersionRef/', views.client_version_ref),
    path(r'clientMatchRunnerVersionRef/', views.client_match_runner_version_ref),
    path(r'clientGetBuildInfo/', views.client_get_build_info),
    path(r'clientWorkerInfo/', views.client_worker_info),
    path(r'clientGetWorkload/', views.client_get_workload),
    path(r'clientGetNetwork/<str:engine>/<str:name>/', views.client_get_network),
    path(r'clientBenchError/', views.client_bench_error),
    path(r'clientSubmitNPS/', views.client_submit_nps),
    path(r'clientSubmitError/', views.client_submit_error),
    path(r'clientSubmitResults/', views.client_submit_results),
    path(r'clientSubmitNPSStats/', views.client_submit_nps_stats),
    path(r'clientHeartbeat/', views.client_heartbeat),
    path(r'clientSubmitPGN/', views.client_submit_pgn),

    # Nice endpoints, which can be hit from the website or with credentials cleanly
    path(r'api/config/', views.api_configs),
    path(r'api/config/<str:engine>/', views.api_configs),
    path(r'api/networks/<str:engine>/', views.api_networks),
    path(r'api/networks/<str:engine>/<str:identifier>/', views.api_network_download),
    path(r'api/networks/<str:engine>/<str:identifier>/compressed/', views.api_network_download, { 'compressed' : True }),
    path(r'api/networks/<str:engine>/<str:identifier>/delete/', views.api_network_delete),
    path(r'api/buildinfo/', views.api_build_info),
    path(r'api/pgns/<int:pgn_id>/', views.api_pgns),
    path(r'api/spsa/<int:workload_id>/<str:query>/', views.api_spsa),
    path(r'api/workload/<int:workload_id>/<str:query>/', views.api_workload),

    # Redirect anything else to the Index
    path(r'', views.index),

    # Link for Ethereal Sales
    path(r'Ethereal/', views.buyEthereal),
]
