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
import OpenBench.utils, OpenBench.stats, OpenBench.models


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

    else:
        dev     = test.dev.source
        base    = test.base.source
        devsha  = test.dev.sha
        basesha = test.base.sha

    repo = OpenBench.utils.pathjoin(*dev.split('/')[:-2])
    return OpenBench.utils.pathjoin(repo, 'compare',
        '{0}...{1}'.format(basesha[:8], devsha[:8]))

def shortStatBlock(test):

    currentllr = twoDigitPrecision(test.currentllr)
    lowerllr   = twoDigitPrecision(test.lowerllr)
    upperllr   = twoDigitPrecision(test.upperllr)
    elolower   = twoDigitPrecision(test.elolower)
    eloupper   = twoDigitPrecision(test.eloupper)

    llrbounds = '({}, {}) '.format(lowerllr, upperllr)

    return 'LLR: {0} {1}[{2}, {3}]\n'.format(currentllr, llrbounds, elolower, eloupper) \
         + 'Games: {0} W: {1} L: {2} D: {3}'.format(test.games, test.wins, test.losses, test.draws)

def longStatBlock(test):

    tokens = test.devoptions.split(' ')
    threads = tokens[0].split('=')[1]
    hash = tokens[1].split('=')[1]

    lower, elo, upper = OpenBench.stats.ELO(test.wins, test.losses, test.draws)
    error = max(upper - elo, elo - lower)

    elo        = twoDigitPrecision(elo)
    error      = twoDigitPrecision(error)
    lowerllr   = twoDigitPrecision(test.lowerllr)
    currentllr = twoDigitPrecision(test.currentllr)
    upperllr   = twoDigitPrecision(test.upperllr)
    elolower   = twoDigitPrecision(test.elolower)
    eloupper   = twoDigitPrecision(test.eloupper)

    return 'ELO   | {0} +- {1} (95%)\n'.format(elo, error) \
         + 'SPRT  | {0}s Threads={1} Hash={2}MB\n'.format(test.timecontrol, threads, hash) \
         + 'LLR   | {0} ({1}, {2}) [{3}, {4}]\n'.format(currentllr, lowerllr, upperllr, elolower, eloupper) \
         + 'Games | N: {0} W: {1} L: {2} D: {3}'.format(test.games, test.wins, test.losses, test.draws) \

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

def testIsFRC(test):
    return "FRC" in test.bookname.upper() or "960" in test.bookname.upper()

def resolveNetworkSha(sha256):
    try: return OpenBench.models.Network.objects.get(sha256=sha256).name
    except: return sha256 # Legacy Networks

def resolveNetworkURL(sha256):
    if OpenBench.models.Network.objects.filter(sha256=sha256):
        return '/networks/download/{0}'.format(sha256)
    return sha256 # Legacy Networks

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
register.filter('testIsFRC', testIsFRC)
register.filter('resolveNetworkSha', resolveNetworkSha)
register.filter('resolveNetworkURL', resolveNetworkURL)

