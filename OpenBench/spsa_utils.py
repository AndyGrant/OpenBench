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

import numpy as np

from OpenBench.models import SPSARun, SPSAParameter

def spsa_param_digest_headers(workload):
    # No real arguments are expected, but this is utilized as a template filter
    return ['Name', 'Curr', 'Start', 'Min', 'Max', 'C', 'C_end', 'R', 'R_end']

def spsa_original_input(workload):

    lines = []
    for param in workload.spsa_run.parameters.order_by('index'):
        lines.append(', '.join([
            param.name,
            'float' if param.is_float else 'int',
            str(param.start),
            str(param.min_value),
            str(param.max_value),
            str(param.c_end),
            str(param.r_end),
        ]))

    return '\n'.join(lines)

def spsa_optimal_values(workload):
    return '\n'.join([
        '%s, %s' % (param.name, param.value if param.is_float else int(round(param.value)))
        for param in workload.spsa_run.parameters.order_by('index')
    ])

def create_spsa_run(workload, request):

    alpha      = float(request.POST['spsa_alpha'])
    gamma      = float(request.POST['spsa_gamma'])
    a_ratio    = float(request.POST['spsa_A_ratio'])
    iterations = int(request.POST['spsa_iterations'])

    spsa_run = SPSARun.objects.create(
        tune              = workload,
        reporting_type    = request.POST['spsa_reporting_type'],
        distribution_type = request.POST['spsa_distribution_type'],
        alpha             = alpha,
        gamma             = gamma,
        iterations        = iterations,
        pairs_per         = int(request.POST['spsa_pairs_per']),
        a_ratio           = a_ratio,
    )

    params = []
    for index, line in enumerate(request.POST['spsa_inputs'].splitlines()):

        name, dtype, value, min_value, max_value, c_end, r_end = map(str.strip, line.split(','))

        c_value   = float(c_end) * iterations ** gamma
        a_end     = float(r_end) * float(c_end) ** 2
        a_value   = float(a_end) * (a_ratio * iterations + iterations) ** alpha

        params.append(SPSAParameter(
            spsa_run  = spsa_run,
            name      = name,
            index     = index,
            value     = float(value),
            is_float  = dtype == 'float',
            start     = float(value),
            min_value = float(min_value),
            max_value = float(max_value),
            c_end     = float(c_end),
            r_end     = float(r_end),
            c_value   = c_value,
            a_value   = a_value,
        ))

    SPSAParameter.objects.bulk_create(params)
    return spsa_run

def spsa_param_digest(workload):

    # C & R, as if we were being assigned a workload right now
    spsa_run      = workload.spsa_run
    iteration     = 1 + (workload.games / (spsa_run.pairs_per * 2))
    c_compression = iteration ** spsa_run.gamma
    r_compression = (spsa_run.a_ratio * spsa_run.iterations + iteration) ** spsa_run.alpha

    digest = []
    for param in spsa_run.parameters.order_by('index'):

        # C and R if we got a workload right now
        c    = max(param.c_value / c_compression, 0.00 if param.is_float else 0.50)
        r    = param.a_value / r_compression / c ** 2
        fstr = '%.4f' if param.is_float else '%d'

        digest.append([
            param.name,
            '%.4f' % (param.value),
            fstr   % (param.start),
            fstr   % (param.min_value),
            fstr   % (param.max_value),
            '%.4f' % (c),
            '%.4f' % (param.c_end),
            '%.4f' % (r),
            '%.4f' % (param.r_end),
        ])

    return digest

def spsa_workload_assignment_dict(workload, runner_count):

    if workload.test_mode != 'SPSA':
        return None

    params = list(workload.spsa_run.parameters.order_by('index'))

    names    = [p.name for p in params]
    values   = np.array([p.value     for p in params])
    mins     = np.array([p.min_value for p in params])
    maxs     = np.array([p.max_value for p in params])
    a_values = np.array([p.a_value   for p in params])
    c_values = np.array([p.c_value   for p in params]) # Scaled later
    is_float = np.array([p.is_float  for p in params])

    # Only use one set of parameters if distribution is SINGLE.
    # Duplicate the params, even though they are the same, across all
    # sockets on the machine, in the event of a singular SPSA distribution

    is_single    = workload.spsa_run.distribution_type == 'SINGLE'
    permutations = 1 if is_single else runner_count
    duplicates   = 1 if not is_single else runner_count

    # C & R are scaled over the course of the iterations
    iteration     = 1 + (workload.games / (workload.spsa_run.pairs_per * 2))
    c_compression = iteration ** workload.spsa_run.gamma
    r_compression = (workload.spsa_run.a_ratio * workload.spsa_run.iterations + iteration) ** workload.spsa_run.alpha

    # Applying scaling
    c_values = np.maximum(c_values / c_compression, np.where(is_float, 0.0, 0.5))
    r_values = a_values / r_compression / c_values**2

    # Apply flips for each parameter, for each permutation
    flips = np.random.choice([-1, 1], size=(len(params), permutations))
    devs  = values[:, None] + flips * c_values[:, None]
    bases = values[:, None] - flips * c_values[:, None]

    # Identify Integers, as they require rounding conversions
    mask_int = ~is_float[:, None] # shape (num_params, 1)
    mask_int = np.broadcast_to(mask_int, devs.shape) # shape (num_params, permutations)

    # Probabilistic rounding for integer parameters
    rand_mat = np.random.rand(len(params), permutations)
    devs[mask_int]  = np.floor(devs[mask_int]  + rand_mat[mask_int])
    bases[mask_int] = np.floor(bases[mask_int] + rand_mat[mask_int])

    # Clip to the original min/max
    devs  = np.clip(devs, mins[:, None], maxs[:, None])
    bases = np.clip(bases, mins[:, None], maxs[:, None])

    # Duplicate if the client will use multiple runners
    devs  = np.repeat(devs , duplicates, axis=1)
    bases = np.repeat(bases, duplicates, axis=1)
    flips = np.repeat(flips, duplicates, axis=1)

    return {
        name : {
            'index' : i,
            'dev'   : [float(x) if is_float[i] else int(x) for x in devs[i]],
            'base'  : [float(x) if is_float[i] else int(x) for x in bases[i]],
            'flip'  : flips[i].tolist(),
            'c'     : float(c_values[i]),
            'r'     : float(r_values[i]),
        } for i, name in enumerate(names)
    }
