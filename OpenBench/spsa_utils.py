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

def spsa_param_digest_headers(workload):
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

def spsa_param_digest(workload):

    # C & R, as if we were being assigned a workload right now
    spsa_run      = workload.spsa_run
    iteration     = 1 + (workload.games / (spsa_run.pairs_per * 2))
    c_compression = iteration ** spsa_run.gamma
    r_compression = (spsa_run.a_value + iteration) ** spsa_run.alpha

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

def spsa_workload_assignment_dict(workload, data):

    params = list(workload.spsa_run.parameters.order_by('index'))

    names  = [p.name for p in params]
    values = np.array([p.value     for p in params])
    mins   = np.array([p.min_value for p in params])
    maxs   = np.array([p.max_value for p in params])
    c_ends = np.array([p.c_end     for p in params])
    r_ends = np.array([p.r_end     for p in params])

    # Only use one set of parameters if distribution is SINGLE.
    # Duplicate the params, even though they are the same, across all
    # sockets on the machine, in the event of a singular SPSA distribution

    is_single    = test.spsa['distribution_type'] == 'SINGLE'
    permutations = 1 if is_single else workload['distribution']['cutechess-count']
    duplicates   = 1 if not is_single else workload['distribution']['cutechess-count']

    # C & R are scaled over the course of the iterations
    iteration     = 1 + (test.games / (test.spsa['pairs_per'] * 2))
    c_compression = iteration ** test.spsa['Gamma']
    r_compression = (test.spsa['A'] + iteration) ** test.spsa['Alpha']