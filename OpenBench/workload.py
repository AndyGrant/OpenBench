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

import OpenBench.views

from OpenBench.models import *

def create_workload(request, workload_type):

    assert workload_type in [ 'TEST', 'TUNE' ]

    if not request.user.is_authenticated:
        return OpenBench.views.redirect(request, '/login/', error='Only enabled users can create tests')

    if not Profile.objects.get(user=request.user).enabled:
        return OpenBench.views.redirect(request, '/login/', error='Only enabled users can create tests')

    if request.method == 'GET':
        data     = { 'networks' : list(Network.objects.all().values()) }
        template = 'create_test.html' if workload_type == 'TEST' else 'create_tune.html'
        return OpenBench.views.render(request, template, data)

    test, errors = OpenBench.utils.create_new_test(request)
    if errors != [] and errors != None:
        return OpenBench.views.redirect(request, '/newTest/', error='\n'.join(errors))

    if warning := OpenBench.utils.branch_is_out_of_date(test):
        warning = 'Consider Rebasing: Dev (%s) appears behind Base (%s)' % (test.dev.name, test.base.name)

    username = request.user.username
    profile  = Profile.objects.get(user=request.user)
    summary  = 'CREATE P=%d TP=%d' % (test.priority, test.throughput)
    LogEvent.objects.create(author=username, summary=summary, log_file='', test_id=test.id)

    if not OpenBench.config.USE_CROSS_APPROVAL and profile.approver:
        test.approved = True; test.save()

    return OpenBench.views.redirect(request, '/index/', warning=warning)

