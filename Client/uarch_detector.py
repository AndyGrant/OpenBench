# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   OpenBench is a chess engine testing framework by Andrew Grant.          #
#   <https://github.com/AndyGrant/OpenBench>  <andrew@grantnet.us>          #
#                                                                           #
#   OpenBench is free software: you can redistribute it and/or modify       #
#   it under the terms of the GNU General Public License as published by    #
#   the Free Software Foundation, either version 3 of the License, or       #
#   (at your option) any later version.                                     #
#                                                                           #
#   OpenBench is distributed in the hope that it will be useful,            #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of          #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           #
#   GNU General Public License for more details.                            #
#                                                                           #
#   You should have received a copy of the GNU General Public License       #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.   #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# Zen microarchitecture detection, from family/model in /proc/cpuinfo. Only
# AMD Zen chips on Linux are detected; anything else returns 'Unknown'

import platform
import traceback

def read_cpuinfo():

    # Fields of the first processor block; all cores share family and model
    info = {}

    for line in open('/proc/cpuinfo'):
        key, sep, value = line.partition(':')
        if not sep:
            break
        info[key.strip()] = value.strip()

    return info

def detect_zen(family, model, flags):

    # Known models are matched first. Unknown models in a known family fall
    # back to telling the generations apart by a feature each one introduced.

    # This mirrors get_amd_cpu() in GCC's:
    # https://github.com/gcc-mirror/gcc/blob/master/gcc/common/config/i386/cpuinfo.h
    # The one addition is Zen+, which GCC folds into znver1.

    if family == 0x17:
        if model <= 0x1f:
            return 'zen+' if model in (0x08, 0x18) else 'zen1'
        if model >= 0x30 or 'clwb' in flags:
            return 'zen2'
        if 'clzero' in flags:
            return 'zen1'

    if family == 0x19:
        if model <= 0x0f:
            return 'zen3'
        if 0x10 <= model <= 0x1f or 0x60 <= model <= 0xaf:
            return 'zen4'
        if 'avx512f' in flags:
            return 'zen4'
        if 'vaes' in flags:
            return 'zen3'

    if family == 0x1a:
        if model <= 0x4f or 0x60 <= model <= 0x77 or 0xd0 <= model <= 0xd7:
            return 'zen5'
        if 0x50 <= model <= 0x5f or 0x80 <= model <= 0xcf or 0xd8 <= model <= 0xe7:
            return 'zen6'
        if 'avx512_vp2intersect' in flags:
            return 'zen5'
        if 'avx512_bmm' in flags:
            return 'zen6'

    return 'Unknown'

def lookup_zen():

    if platform.system() != 'Linux':
        return 'Unknown'

    info = read_cpuinfo()

    if info['vendor_id'] != 'AuthenticAMD':
        return 'Unknown'

    return detect_zen(int(info['cpu family']), int(info['model']), info['flags'].split())

def detect_uarch():

    try:
        return lookup_zen()

    except:
        # Detection is best-effort, so a bad probe never crashes the worker
        print('Failed to detect micro-architecture')
        traceback.print_exc()

    return 'Unknown'

if __name__ == '__main__':

    print(detect_uarch())
