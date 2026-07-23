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

from collections import defaultdict

from django.db.models import BooleanField, ExpressionWrapper, F, Q
from django.utils import timezone

import OpenBench.views
import OpenBench.stats
from OpenBench.models import *

def view_workload(request, workload, workload_type):

    assert workload_type in [ 'TEST', 'TUNE', 'DATAGEN' ]

    # The individual per-machine Result rows are never sent with the page; they
    # are fetched on demand via the "Fetch Individual Results" button. The
    # aggregate summary is fetched automatically once the page loads.

    data = {
        'workload' : workload,
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

def fetch_results(workload):

    # One minute prior to now
    target = datetime.datetime.utcnow()
    target = target.replace(tzinfo=timezone.utc)
    target = target - datetime.timedelta(minutes=1)

    # Create `active` field for current machines
    qs = Result.objects.filter(test=workload).select_related('machine__user').annotate(
        active=ExpressionWrapper(
            Q(machine__updated__gte=target) &
            Q(test_id=F('machine__workload')),
            output_field=BooleanField()
        )
    )

    # Drop Results that have played nothing and are no longer active
    qs = qs.filter(Q(games__gt=0) | Q(active=True))

    # Hand back the raw pentanomial buckets; the individual results table is
    # formatted client-side in OpenBench/static/workload_utils.js
    qs = qs.values(
        'machine__id',
        'machine__user__username',
        'games',
        'LL', 'LD', 'DD', 'DW', 'WW',
        'timeloss',
        'crashes',
        'active',
    )

    return list(qs)

def fetch_result_summaries(workload):

    # Aggregate the pentanomial counters across every Result of the workload,
    # grouped three ways: by the User who ran it, and by the reporting Machine's
    # cpu_name and isa_name. We only ever sum penta; the trinomial counts and
    # crash/timeloss/active fields are intentionally left out.
    qs = Result.objects.filter(test=workload).select_related('machine__user')
    qs = qs.values(
        'machine__user__username',
        'machine__info',
        'LL', 'LD', 'DD', 'DW', 'WW',
    )

    by_user = defaultdict(lambda: [0, 0, 0, 0, 0])
    by_cpu  = defaultdict(lambda: [0, 0, 0, 0, 0])
    by_isa  = defaultdict(lambda: [0, 0, 0, 0, 0])

    def accumulate(bucket, key, penta):
        total = bucket[key if key else 'Unknown']
        for i in range(5):
            total[i] += penta[i]

    for row in qs:
        penta = (row['LL'], row['LD'], row['DD'], row['DW'], row['WW'])
        info  = row['machine__info'] or {}
        accumulate(by_user, row['machine__user__username'], penta)
        accumulate(by_cpu,  info.get('cpu_name'),           penta)
        accumulate(by_isa,  info.get('isa_name'),           penta)

    # Turn a { key: penta } bucket into ready-to-display rows: the penta as a
    # single "(a, b, c, d, e)" string, a point-estimate Elo with its symmetric
    # error bar, the pair count, and the share of the grouping's total. Largest
    # contributor comes first.

    def elo_display(penta):
        lower, mu, upper = OpenBench.stats.Elo(penta)
        return '%.2f ± %.2f' % (mu, (upper - lower) / 2)

    def summarize(bucket):
        total_pairs = sum(sum(penta) for penta in bucket.values())
        rows = [{
            'key'     : key,
            'penta'   : '(%d, %d, %d, %d, %d)' % tuple(penta),
            'elo'     : elo_display(penta),
            'pairs'   : sum(penta),
            'percent' : '%.2f' % (100.0 * sum(penta) / total_pairs if total_pairs else 0.0),
        } for key, penta in bucket.items()]
        return sorted(rows, key=lambda row: row['pairs'], reverse=True)

    return {
        'user'     : summarize(by_user),
        'cpu_name' : summarize(by_cpu),
        'isa_name' : summarize(by_isa),
    }
