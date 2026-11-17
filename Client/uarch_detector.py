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

# Microarchitecture detection, from family/model in /proc/cpuinfo. Only AMD Zen
# and Intel chips new enough to have AVX2 (Haswell and later), on Linux, are
# detected; anything else returns 'Unknown'

import platform
import traceback

# Every name detect_uarch() can return

UARCH_NAMES = [
    'zen1',          'zen+',            'zen2',           'zen3',
    'zen4',          'zen5',            'zen6',           'haswell',
    'broadwell',     'skylake',         'skylake-avx512', 'cascadelake',
    'cooperlake',    'cannonlake',      'icelake-client', 'icelake-server',
    'rocketlake',    'tigerlake',       'alderlake',      'sapphirerapids',
    'graniterapids', 'graniterapids-d', 'arrowlake',      'arrowlake-s',
    'pantherlake',   'sierraforest',    'grandridge',     'clearwaterforest',
    'novalake',      'diamondrapids',   'Unknown',
]

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

def detect_intel(family, model, flags):

    # Intel microarchitectures as (name, family, models), as in get_intel_cpu() in
    # GCC's cpuinfo.h, with everything that predates AVX2 left out. Names are GCC's,
    # so several products can share one name; the comment on each row is the product
    # GCC's source gives for those models. Model 0x55 is handled in detect_intel()

    INTEL_UARCHS = [
        ('haswell',          0x06, (0x3c, 0x3f, 0x45, 0x46)), # Haswell
        ('broadwell',        0x06, (0x3d, 0x47, 0x4f, 0x56)), # Broadwell
        ('skylake',          0x06, (0x4e, 0x5e)),             # Skylake
        ('skylake',          0x06, (0x8e, 0x9e)),             # Kaby Lake
        ('skylake',          0x06, (0xa5, 0xa6)),             # Comet Lake
        ('cannonlake',       0x06, (0x66,)),                  # Cannon Lake
        ('icelake-client',   0x06, (0x7d, 0x7e, 0x9d)),       # Ice Lake client
        ('icelake-server',   0x06, (0x6a, 0x6c)),             # Ice Lake server
        ('rocketlake',       0x06, (0xa7,)),                  # Rocket Lake
        ('tigerlake',        0x06, (0x8c, 0x8d)),             # Tiger Lake
        ('alderlake',        0x06, (0x97, 0x9a)),             # Alder Lake
        ('alderlake',        0x06, (0xbe,)),                  # Alder Lake N
        ('alderlake',        0x06, (0xb7, 0xba, 0xbf)),       # Raptor Lake
        ('alderlake',        0x06, (0xaa, 0xac)),             # Meteor Lake
        ('sapphirerapids',   0x06, (0x8f,)),                  # Sapphire Rapids
        ('sapphirerapids',   0x06, (0xcf,)),                  # Emerald Rapids
        ('graniterapids',    0x06, (0xad,)),                  # Granite Rapids
        ('graniterapids-d',  0x06, (0xae,)),                  # Granite Rapids D
        ('arrowlake',        0x06, (0xb5, 0xc5)),             # Arrow Lake
        ('arrowlake-s',      0x06, (0xc6,)),                  # Arrow Lake S
        ('arrowlake-s',      0x06, (0xbd,)),                  # Lunar Lake
        ('pantherlake',      0x06, (0xcc,)),                  # Panther Lake
        ('pantherlake',      0x06, (0xd5,)),                  # Wildcat Lake
        ('sierraforest',     0x06, (0xaf,)),                  # Sierra Forest
        ('grandridge',       0x06, (0xb6,)),                  # Grand Ridge
        ('clearwaterforest', 0x06, (0xdd,)),                  # Clearwater Forest
        ('novalake',         0x12, (0x01, 0x03)),             # Nova Lake
        ('diamondrapids',    0x13, (0x01,)),                  # Diamond Rapids
    ]

    # Model 0x55 is every Skylake-X and later Xeon Scalable, until Ice Lake.
    # Later AVX-512 extensions are what tell the generations apart.

    if (family, model) == (6, 0x55):
        if 'avx512_bf16' in flags:
            return 'cooperlake'
        if 'avx512_vnni' in flags:
            return 'cascadelake'
        return 'skylake-avx512'

    for name, uarch_family, models in INTEL_UARCHS:
        if family == uarch_family and model in models:
            return name

    return 'Unknown'

def lookup_uarch():

    if platform.system() != 'Linux':
        return 'Unknown'

    info   = read_cpuinfo()
    family = int(info['cpu family'])
    model  = int(info['model'])
    flags  = info['flags'].split()

    if info['vendor_id'] == 'AuthenticAMD':
        return detect_zen(family, model, flags)

    if info['vendor_id'] == 'GenuineIntel':
        return detect_intel(family, model, flags)

    return 'Unknown'

def detect_uarch():

    try:
        return lookup_uarch()

    except:
        # Detection is best-effort, so a bad probe never crashes the worker
        print('Failed to detect micro-architecture')
        traceback.print_exc()

    return 'Unknown'

if __name__ == '__main__':

    print(detect_uarch())
