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

    if type(test) != OpenBench.models.Test:
        dev     = test['dev']['source']
        base    = test['base']['source']
        devsha  = test['dev']['sha']
        basesha = test['base']['sha']
        engine  = test['dev_engine']

    else:
        dev     = test.dev.source
        base    = test.base.source
        devsha  = test.dev.sha
        basesha = test.base.sha
        engine  = test.dev_engine

    if OpenBench.config.OPENBENCH_CONFIG['engines'][engine]['private']:
        repo = OpenBench.config.OPENBENCH_CONFIG['engines'][engine]['source']
    else:
        repo = OpenBench.utils.path_join(*dev.split('/')[:-2])

    return OpenBench.utils.path_join(repo, 'compare',
        '{0}...{1}'.format(basesha[:8], devsha[:8]))

def shortStatBlock(test):

    if test.test_mode == "SPRT":

        currentllr = twoDigitPrecision(test.currentllr)
        lowerllr   = twoDigitPrecision(test.lowerllr)
        upperllr   = twoDigitPrecision(test.upperllr)
        elolower   = twoDigitPrecision(test.elolower)
        eloupper   = twoDigitPrecision(test.eloupper)

        llrbounds = '({}, {}) '.format(lowerllr, upperllr)

        return 'LLR: {0} {1}[{2}, {3}]\n'.format(currentllr, llrbounds, elolower, eloupper) \
             + 'Games: {0} W: {1} L: {2} D: {3}'.format(test.games, test.wins, test.losses, test.draws)

    if test.test_mode == "GAMES":

        lower, elo, upper = OpenBench.stats.ELO(test.wins, test.losses, test.draws)
        error = max(upper - elo, elo - lower)

        elo   = twoDigitPrecision(elo)
        error = twoDigitPrecision(error)

        return 'Elo: {0} +- {1} (95%) [N={2}]\n'.format(elo, error, test.max_games) \
             + 'Games: {0} W: {1} L: {2} D: {3}'.format(test.games, test.wins, test.losses, test.draws)

def longStatBlock(test):

    threads = OpenBench.utils.extract_option(test.dev_options, 'Threads')
    hash    = OpenBench.utils.extract_option(test.dev_options, 'Hash')

    lower, elo, upper = OpenBench.stats.ELO(test.wins, test.losses, test.draws)
    error = max(upper - elo, elo - lower)

    elo   = twoDigitPrecision(elo)
    error = twoDigitPrecision(error)

    if test.test_mode == 'SPRT':

        lowerllr    = twoDigitPrecision(test.lowerllr)
        currentllr  = twoDigitPrecision(test.currentllr)
        upperllr    = twoDigitPrecision(test.upperllr)
        elolower    = twoDigitPrecision(test.elolower)
        eloupper    = twoDigitPrecision(test.eloupper)
        timecontrol = test.dev_time_control + ['s', '']['=' in test.dev_time_control]

        return 'ELO   | {0} +- {1} (95%)\n'.format(elo, error) \
             + 'SPRT  | {0} Threads={1} Hash={2}MB\n'.format(timecontrol, threads, hash) \
             + 'LLR   | {0} ({1}, {2}) [{3}, {4}]\n'.format(currentllr, lowerllr, upperllr, elolower, eloupper) \
             + 'GAMES | N: {0} W: {1} L: {2} D: {3}'.format(test.games, test.wins, test.losses, test.draws)

    if test.test_mode == 'GAMES':

        timecontrol = test.dev_time_control + ['s', '']['=' in test.dev_time_control]

        return 'ELO   | {0} +- {1} (95%)\n'.format(elo, error) \
             + 'CONF  | {0} Threads={1} Hash={2}MB\n'.format(timecontrol, threads, hash) \
             + 'GAMES | N: {0} W: {1} L: {2} D: {3}'.format(test.games, test.wins, test.losses, test.draws)

def testResultColour(test):

    if test.passed: return 'green'
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
