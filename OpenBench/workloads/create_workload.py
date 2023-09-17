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

# Module serves a singular purpose, to invoke: create_workload(request, type)
#
# A Workload can be a "TEST", which is an SPRT, or FIXED type.
# A Workload can be a "TUNE", which is an SPSA tuning session
#
# This module will either create the workload and return the user to the index,
# which will display their newly created test. Or it will return them to index,
# with a list of errors that need to be fixed. A warning may also be displayed,
# if the Base branch appears ahead of the Dev branch.

import math

import OpenBench.utils
import OpenBench.views

from OpenBench.models import *
from OpenBench.workloads.verify_workload import verify_workload

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

    if workload_type == 'TEST':
        workload, errors = create_new_test(request)

    if workload_type == 'TUNE':
        workload, errors = create_new_tune(request)

    if errors != [] and errors != None:
        url = '/newTest/' if workload_type == 'TEST' else '/newTune/'
        return OpenBench.views.redirect(request, url, error='\n'.join(errors))

    if warning := OpenBench.utils.branch_is_out_of_date(workload):
        warning = 'Consider Rebasing: Dev (%s) appears behind Base (%s)' % (workload.dev.name, workload.base.name)

    username = request.user.username
    profile  = Profile.objects.get(user=request.user)
    summary  = 'CREATE P=%d TP=%d' % (workload.priority, workload.throughput)
    LogEvent.objects.create(author=username, summary=summary, log_file='', test_id=workload.id)

    if not OpenBench.config.USE_CROSS_APPROVAL and profile.approver:
        workload.approved = True; workload.save()

    return OpenBench.views.redirect(request, '/index/', warning=warning)

def create_new_test(request):

    # Collects erros, and collects all data from the Github API
    errors, engine_info = verify_workload(request, 'TEST')
    dev_info, dev_has_all = engine_info[0]
    base_ingo, base_has_all = engine_info[1]

    if errors:
        return None, errors

    test                   = Test()
    test.author            = request.user.username
    test.book_name         = request.POST['book_name']

    test.dev               = get_engine(*dev_info)
    test.dev_repo          = request.POST['dev_repo']
    test.dev_engine        = request.POST['dev_engine']
    test.dev_options       = request.POST['dev_options']
    test.dev_network       = request.POST['dev_network']
    test.dev_time_control  = OpenBench.utils.TimeControl.parse(request.POST['dev_time_control'])

    test.base              = get_engine(*base_ingo)
    test.base_repo         = request.POST['base_repo']
    test.base_engine       = request.POST['base_engine']
    test.base_options      = request.POST['base_options']
    test.base_network      = request.POST['base_network']
    test.base_time_control = OpenBench.utils.TimeControl.parse(request.POST['base_time_control'])

    test.worker_limit      = 0 if request.POST['worker_limit'] == 'None' else int(request.POST['worker_limit'])
    test.thread_limit      = 0 if request.POST['thread_limit'] == 'None' else int(request.POST['thread_limit'])
    test.workload_size     = int(request.POST['workload_size'])
    test.priority          = int(request.POST['priority'])
    test.throughput        = int(request.POST['throughput'])

    test.syzygy_wdl        = request.POST['syzygy_wdl']
    test.syzygy_adj        = request.POST['syzygy_adj']
    test.win_adj           = request.POST['win_adj']
    test.draw_adj          = request.POST['draw_adj']

    test.test_mode         = request.POST['test_mode']
    test.awaiting          = not (dev_has_all and base_has_all)

    if test.test_mode == 'SPRT':
        test.elolower = float(request.POST['test_bounds'].split(',')[0].lstrip('['))
        test.eloupper = float(request.POST['test_bounds'].split(',')[1].rstrip(']'))
        test.alpha    = float(request.POST['test_confidence'].split(',')[1].rstrip(']'))
        test.beta     = float(request.POST['test_confidence'].split(',')[0].lstrip('['))
        test.lowerllr = math.log(test.beta / (1.0 - test.alpha))
        test.upperllr = math.log((1.0 - test.beta) / test.alpha)

    if test.test_mode == 'GAMES':
        test.max_games = int(request.POST['test_max_games'])

    if test.dev_network:
        test.dev_netname = Network.objects.get(engine=test.dev_engine, sha256=test.dev_network).name

    if test.base_network:
        test.base_netname = Network.objects.get(engine=test.base_engine, sha256=test.base_network).name

    test.save()

    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    return test, None

def create_new_tune(request):

    # Collects erros, and collects all data from the Github API
    errors, engine_info = verify_workload(request, 'TUNE')
    dev_info, dev_has_all = engine_info

    if errors:
        return None, errors

    test                  = Test()
    test.author           = request.user.username
    test.book_name        = request.POST['book_name']

    test.dev              = test.base              = get_engine(*dev_info)
    test.dev_repo         = test.base_repo         = request.POST['dev_repo']
    test.dev_engine       = test.base_engine       = request.POST['dev_engine']
    test.dev_options      = test.base_options      = request.POST['dev_options']
    test.dev_network      = test.base_network      = request.POST['dev_network']
    test.dev_time_control = test.base_time_control = OpenBench.utils.TimeControl.parse(request.POST['dev_time_control'])

    test.worker_limit     = 0 if request.POST['worker_limit'] == 'None' else int(request.POST['worker_limit'])
    test.thread_limit     = 0 if request.POST['thread_limit'] == 'None' else int(request.POST['thread_limit'])
    test.workload_size    = int(request.POST['spsa_pairs_per'])
    test.priority         = int(request.POST['priority'])
    test.throughput       = int(request.POST['throughput'])

    test.syzygy_wdl       = request.POST['syzygy_wdl']
    test.syzygy_adj       = request.POST['syzygy_adj']
    test.win_adj          = request.POST['win_adj']
    test.draw_adj         = request.POST['draw_adj']

    test.test_mode        = 'SPSA'
    test.spsa             = extract_spas_params(request)

    test.awaiting         = not dev_has_all

    if test.dev_network:
        name = Network.objects.get(engine=test.dev_engine, sha256=test.dev_network).name
        test.dev_netname = test.base_netname = name

    test.save()

    profile = Profile.objects.get(user=request.user)
    profile.tests += 1
    profile.save()

    return test, None

def extract_spas_params(request):

    spsa = {} # SPSA Hyperparams
    spsa['Alpha'  ] = float(request.POST['spsa_alpha'])
    spsa['Gamma'  ] = float(request.POST['spsa_gamma'])
    spsa['A_ratio'] = float(request.POST['spsa_A_ratio'])

    # Tuning durations
    spsa['iterations'] = int(request.POST['spsa_iterations'])
    spsa['pairs_per' ] = int(request.POST['spsa_pairs_per'])
    spsa['A'         ] = spsa['A_ratio'] * spsa['iterations']

    # Each individual tuning parameter
    spsa['parameters'] = {}
    for line in request.POST['spsa_inputs'].split('\n'):

        # Comma-seperated values, already verified in verify_workload()
        name, value, minimum, maximum, c_end, r_end = line.split(',')

        param          = {} # Raw extraction
        param['start'] = float(value)
        param['value'] = float(value)
        param['min'  ] = float(minimum)
        param['max'  ] = float(maximum)
        param['c_end'] = float(c_end)
        param['r_end'] = float(r_end)

        # Verbatim Fishtest logic for computing these
        param['c']     = param['c_end'] * spsa['iterations'] ** spsa['Gamma']
        param['a_end'] = param['r_end'] * param['c_end'] ** 2
        param['a']     = param['a_end'] * (spsa['A'] + spsa['iterations']) ** spsa['Alpha']

        spsa['parameters'][name] = param

    return spsa

def get_engine(source, name, sha, bench):

    engine = Engine.objects.filter(name=name, source=source, sha=sha, bench=bench)
    if engine.first() != None:
        return engine.first()

    return Engine.objects.create(name=name, source=source, sha=sha, bench=bench)
