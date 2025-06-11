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
        '%s, %f' % (param.name, param.value if param.is_float else round(param.value))
        for param in workload.spsa_run.parameters.order_by('index')
    ])
