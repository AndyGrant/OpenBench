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

import re, django
import OpenBench.config, OpenBench.utils, OpenBench.stats, OpenBench.models

def oneDigitPrecision(value):
    try:
        value = round(value, 1)
        if '.' not in str(value):
            return str(value) + '.0'
        pre, post = str(value).split('.')
        post += '0'
        return pre + '.' + post[0:1]
    except:
        return value

def twoDigitPrecision(value):
    try:
        value = round(value, 2)
        if '.' not in str(value):
            return str(value) + '.00'
        pre, post = str(value).split('.')
        post += '00'
        return pre + '.' + post[0:2]
    except:
        return value

def gitDiffLink(test):

    engines = OpenBench.config.OPENBENCH_CONFIG['engines']

    if test.dev_engine in engines and engines[test.dev_engine]['private']:
        repo = OpenBench.config.OPENBENCH_CONFIG['engines'][test.dev_engine]['source']
    else:
        repo = OpenBench.utils.path_join(*test.dev.source.split('/')[:-2])

    if test.test_mode == 'SPSA':
        return OpenBench.utils.path_join(repo, 'compare', test.dev.sha[:8])

    return OpenBench.utils.path_join(repo, 'compare',
        '{0}..{1}'.format( test.base.sha[:8], test.dev.sha[:8]))

def shortStatBlock(test):

    if test.test_mode == 'SPSA':
        return '\n'.join([
            'Tuning %d Parameters' % (len(test.spsa['parameters'].keys())),
            '%d/%d Iterations' % (test.games / (2 * test.spsa['pairs_per']), test.spsa['iterations']),
            '%d/%d Games Played' % (test.games, 2 * test.spsa['iterations'] * test.spsa['pairs_per'])])

    if test.test_mode == 'SPRT':
        top_line = 'LLR: %0.2f (%0.2f, %0.2f) [%0.2f, %0.2f]' % (
            test.currentllr, test.lowerllr, test.upperllr, test.elolower, test.eloupper)

    if test.test_mode == 'GAMES':
        lower, elo, upper = OpenBench.stats.ELO([test.losses, test.draws, test.wins])
        top_line = 'Elo: %0.2f +- %0.2f (95%%) [N=%d]' % (elo, max(upper - elo, elo - lower), test.max_games)

    tri_line   = 'Games: %d W: %d L: %d D: %d' % (test.games, test.wins, test.losses, test.draws)
    penta_line = 'Pntml(0-2): %d, %d, %d, %d, %d' % (test.LL, test.LD, test.DD, test.DW, test.WW)

    if test.use_penta:
        return '\n'.join([top_line, tri_line, penta_line])

    if test.use_tri:
        return '\n'.join([top_line, tri_line])

    return 'Test uses neither Trinomoal nor Pentanomial'

def longStatBlock(test):

    assert test.test_mode != 'SPSA'

    threads     = int(OpenBench.utils.extract_option(test.dev_options, 'Threads'))
    hashmb      = int(OpenBench.utils.extract_option(test.dev_options, 'Hash'))
    timecontrol = test.dev_time_control + ['s', '']['=' in test.dev_time_control]
    test_type   = 'SPRT' if test.test_mode == 'SPRT' else 'Conf'

    lower, elo, upper = OpenBench.stats.ELO([test.losses, test.draws, test.wins])

    lines = [
        'Elo   | %0.2f +- %0.2f (95%%)' % (elo, max(upper - elo, elo - lower)),
        '%-5s | %s Threads=%d Hash=%dMB' % (test_type, timecontrol, threads, hashmb),
    ]

    if test.test_mode == 'SPRT':
        lines.append('LLR   | %0.2f (%0.2f, %0.2f) [%0.2f, %0.2f]' % (
            test.currentllr, test.lowerllr, test.upperllr, test.elolower, test.eloupper))

    lines.append('Games | N: %d W: %d L: %d D: %d' % (test.games, test.wins, test.losses, test.draws))

    if test.use_penta:
        lines.append('Penta | [%d, %d, %d, %d, %d]' % (test.LL, test.LD, test.DD, test.DW, test.WW))

    return '\n'.join(lines)

    return 'Test uses neither Trinomoal nor Pentanomial'

def testResultColour(test):

    if test.passed:
        if test.elolower + test.eloupper < 0: return 'blue'
        return 'green'
    if test.failed:
        if test.wins >= test.losses: return 'yellow'
        return 'red'
    return ''

def sumAttributes(iterable, attribute):
    try: return sum([getattr(f, attribute) for f in iterable])
    except: return 0

def insertCommas(value):
    return '{:,}'.format(int(value))

def prettyName(name):
    if re.search('[0-9a-fA-F]{40}', name):
        return name[:16].upper()
    return name

def prettyDevName(test):

    # If engines are different, use the base name + branch
    if test.dev_engine != test.base_engine:
        return '[%s] %s' % (test.base_engine, test.base.name)

    # If testing different Networks, possibly use the Network name
    if test.dev.name == test.base.name and test.dev_netname != '':

        # Nets match as well, so revert back to the branch name
        if test.dev_network == test.base_network:
            return prettyName(test.dev.name)

        # Use the network's name, if we still have it saved
        try: return OpenBench.models.Network.objects.get(sha256=test.dev_network).name
        except: return test.dev_netname # File has since been deleted ?

    return prettyName(test.dev.name)

def testIsFRC(test):
    return "FRC" in test.book_name.upper() or "960" in test.book_name.upper()

def resolveNetworkURL(sha256):
    if OpenBench.models.Network.objects.filter(sha256=sha256):
        return '/networks/download/{0}'.format(sha256)
    return sha256 # Legacy Networks

def testIdToPrettyName(test_id):
    return prettyName(OpenBench.models.Test.objects.get(id=test_id).dev.name)

def testIdToTimeControl(test_id):
    return OpenBench.models.Test.objects.get(id=test_id).dev_time_control

def cpuflagsBlock(machine, N=8):

    reported = []
    flags    = machine.info['cpu_flags']

    general_flags   = ['BMI2', 'POPCNT']
    broad_avx_flags = ['AVX2', 'AVX', 'SSE4_2', 'SSE4_1', 'SSSE3']

    for flag in general_flags:
        if flag in flags:
            reported.append(flag)
            break

    for flag in broad_avx_flags:
        if flag in flags:
            reported.append(flag)
            break

    for flag in flags:
        if flag not in general_flags and flag not in broad_avx_flags:
            reported.append(flag)

    return ' '.join(reported)

def compilerBlock(machine):
    string = ''
    for engine, info in machine.info['compilers'].items():
        string += '%-16s %-8s (%s)\n' % (engine, info[0], info[1])
    return string

def removePrefix(value, prefix):
    return value.removeprefix(prefix)

def machine_name(machine_id):
    try:
        machine = OpenBench.models.Machine.objects.get(id=machine_id)
        return machine.info['machine_name']
    except: return 'None'


register = django.template.Library()
register.filter('oneDigitPrecision', oneDigitPrecision)
register.filter('twoDigitPrecision', twoDigitPrecision)
register.filter('gitDiffLink', gitDiffLink)
register.filter('shortStatBlock', shortStatBlock)
register.filter('longStatBlock', longStatBlock)
register.filter('testResultColour', testResultColour)
register.filter('sumAttributes', sumAttributes)
register.filter('insertCommas', insertCommas)
register.filter('prettyName', prettyName)
register.filter('prettyDevName', prettyDevName)
register.filter('testIsFRC', testIsFRC)
register.filter('resolveNetworkURL', resolveNetworkURL)
register.filter('testIdToPrettyName', testIdToPrettyName)
register.filter('testIdToTimeControl', testIdToTimeControl)
register.filter('cpuflagsBlock', cpuflagsBlock)
register.filter('compilerBlock', compilerBlock)
register.filter('removePrefix', removePrefix)
register.filter('machine_name', machine_name)

####

def spsa_param_digest(test):

    digest = []

    # C and R are compressed as we progress iterations
    iteration     = 10000 + (test.games / (test.spsa['pairs_per'] * 2))
    c_compression = iteration ** test.spsa['Gamma']
    r_compression = (test.spsa['A'] + iteration) ** test.spsa['Alpha']

    # Maintain the original order, if there was one
    keys = sorted(
        test.spsa['parameters'].keys(),
        key=lambda x: test.spsa['parameters'][x].get('index', -1)
    )

    for name in keys:

        param = test.spsa['parameters'][name]

        # C and R if we got a workload right now
        c = param['c'] / c_compression
        r = param['a'] / r_compression / c ** 2

        fstr = '%.4f' if param['float'] else '%d'

        digest.append([
            name,
            '%.4f' % (param['value']),
            fstr   % (param['start']),
            fstr   % (param['min'  ]),
            fstr   % (param['max'  ]),
            '%.4f' % (c),
            '%.4f' % (param['c_end']),
            '%.4f' % (r),
            '%.4f' % (param['r_end']),
        ])

    return digest

def spsa_original_input(test):

    # Maintain the original order, if there was one
    keys = sorted(
        test.spsa['parameters'].keys(),
        key=lambda x: test.spsa['parameters'][x].get('index', -1)
    )

    lines = []
    for name in keys:

        param = test.spsa['parameters'][name]
        dtype = 'float' if param['float'] else 'int'

        # Original 7 token Input
        lines.append(', '.join([
            name,
            dtype,
            str(param['start']),
            str(param['min'  ]),
            str(param['max'  ]),
            str(param['c_end']),
            str(param['r_end']),
        ]))

    return '\n'.join(lines)

def book_download_link(test):
    return OpenBench.config.OPENBENCH_CONFIG['books'][test.book_name]['source']


register.filter('spsa_param_digest', spsa_param_digest)
register.filter('spsa_original_input', spsa_original_input)
register.filter('book_download_link', book_download_link)





