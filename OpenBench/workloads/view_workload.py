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

# Module serves a singular purpose, to invoke:
# >>> view_workload(request, workload, type)
#
# A Workload can be a "TEST", which is an SPRT, or FIXED type
# A Workload can be a "TUNE", which is an SPSA tuning session
# A Workload can be a "DATAGEN", which is a Data Generation session

import datetime
import json

from django.db.models import BooleanField, ExpressionWrapper, F, Q
from django.utils import timezone

import OpenBench.views
from OpenBench.models import *

def view_workload(request, workload, workload_type):

    assert workload_type in [ 'TEST', 'TUNE', 'DATAGEN' ]

    truncated, results = fetch_results(workload, force=False)

    data = {
        'workload'          : workload,
        'results'           : json.dumps(results),
        'results_truncated' : truncated
    }

    if workload_type == 'TEST':
        data['type']= workload_type
        data['dev_text'] = 'Dev'

    if workload_type == 'TUNE':
        data['type'] = workload_type
        data['dev_text'] = ''

    if workload_type == 'DATAGEN':
        data['type'] = workload_type
        data['dev_text'] = 'Dev'

    return OpenBench.views.render(request, 'workload.html', data)

def fetch_results(workload, force):

    # Bail out when there are a large number of results, unless `force`
    qs = Result.objects.filter(test=workload)
    if not force and qs.count() > 25:
        return True, []

    # One minute prior to now
    target = datetime.datetime.utcnow()
    target = target.replace(tzinfo=timezone.utc)
    target = target - datetime.timedelta(minutes=1)

    # Create `active` field for current machines
    qs = qs.select_related('machine__user').annotate(
        active=ExpressionWrapper(
            Q(machine__updated__gte=target) &
            Q(test_id=F('machine__workload')),
            output_field=BooleanField()
        )
    )

    # Only the fields consumed by the template OpenBench/workload.html
    qs = qs.values(
        'machine__id',
        'machine__user__username',
        'updated',
        'games',
        'wins',
        'losses',
        'draws',
        'timeloss',
        'crashes',
        'active',
    )

    results = [{ **result, 'updated' : result['updated'].timestamp() } for result in qs]

    return False, results