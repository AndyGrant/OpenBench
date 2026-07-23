# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
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

# This ISA detector is derived from Stockfish's efforts, and follows the same
# ISA names and matching order it establishes. Original detection can be seen
# at: official-stockfish/Stockfish's scripts/get_native_properties.sh

import subprocess
import traceback

def native_macros(cxx):

    # Ask the compiler for every macro it defines under -march=native, without
    # actually compiling anything. Output is a series of "#define NAME VALUE".

    cmd    = [cxx, '-march=native', '-dM', '-E', '-']
    proc   = subprocess.run(cmd, input=b'', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return proc.stdout.decode('ascii', errors='ignore')

def macro_defined(macros, name):

    # -dM output is a series of "#define NAME VALUE" lines. The trailing space
    # ensures e.g. __AVX512F__ does not spuriously match __AVX512FOO__.
    return ('#define %s ' % (name)) in macros

def macro_value(macros, name):

    # Return the VALUE of a "#define NAME VALUE" line, or None if not defined.
    token = '#define %s ' % (name)
    for line in macros.splitlines():
        if line.startswith(token):
            return line[len(token):].strip()
    return None


def get_arch(macros):

    # Coarse platform selection from the compiler's target macros. This only
    # tells us which family of ISAs to consider; the specific ISA is decided
    # from the remaining macros below.

    if macro_defined(macros, '__x86_64__') or macro_defined(macros, '__i386__'):
        return 'x86'

    if macro_defined(macros, '__aarch64__') or macro_defined(macros, '__arm__'):
        return 'ARM'

def has_slow_pext(macros):

    # Zen1/Zen2 and the Bulldozer family (Bulldozer, Piledriver, Steamroller,
    # Excavator) implement BMI2's PEXT/PDEP in microcode, making them slow. The
    # compiler tells us the exact micro-architecture it tuned for via a
    # predefined macro such as __znver1 or __bdver4.

    slow = ('__znver1', '__znver2', '__bdver1', '__bdver2', '__bdver3', '__bdver4')
    return any(arch in macros for arch in slow)


def detect_isa_x86(macros):

    def has(*required):
        return all(macro_defined(macros, macro) for macro in required)

    # 32-bit x86 has a much shorter ladder of its own
    if not macro_defined(macros, '__x86_64__'):

        if has('__SSE4_1__', '__POPCNT__'):
            return 'x86-32-sse41-popcnt'

        if has('__SSE2__'):
            return 'x86-32-sse2'

        return 'x86-32'

    # Ordered strongest -> weakest; first match wins
    if has('__AVX512F__', '__AVX512CD__', '__AVX512VL__', '__AVX512DQ__', '__AVX512BW__',
           '__AVX512IFMA__', '__AVX512VBMI__', '__AVX512VBMI2__', '__AVX512VPOPCNTDQ__',
           '__AVX512BITALG__', '__AVX512VNNI__', '__VPCLMULQDQ__', '__GFNI__', '__VAES__'):
        return 'x86-64-avx512icl'

    if has('__AVX512VNNI__', '__AVX512DQ__', '__AVX512F__', '__AVX512BW__', '__AVX512VL__'):
        return 'x86-64-vnni512'

    if has('__AVX512F__', '__AVX512BW__'):
        return 'x86-64-avx512'

    if has('__AVXVNNI__'):
        return 'x86-64-avxvnni'

    if has('__BMI2__') and not has_slow_pext(macros):
        return 'x86-64-bmi2'

    if has('__AVX2__'):
        return 'x86-64-avx2'

    if has('__SSE4_1__', '__POPCNT__'):
        return 'x86-64-sse41-popcnt'

    if has('__SSSE3__'):
        return 'x86-64-ssse3'

    if has('__SSE3__', '__POPCNT__'):
        return 'x86-64-sse3-popcnt'

    return 'x86-64'

def detect_isa_arm(macros):

    # aarch64 is always ARMv8+; the only distinction we draw is the presence
    # of the dot-product extension (SF's asimddp flag -> __ARM_FEATURE_DOTPROD).
    if macro_defined(macros, '__aarch64__'):
        if macro_defined(macros, '__ARM_FEATURE_DOTPROD'):
            return 'armv8-dotprod'
        return 'armv8'

    # 32-bit ARM. __ARM_ARCH holds the architecture level (5/6/7/8), and
    # __ARM_NEON tells us whether NEON (Advanced SIMD) is available.
    try:
        level = int(macro_value(macros, '__ARM_ARCH'))
    except (TypeError, ValueError):
        level = None

    neon = macro_defined(macros, '__ARM_NEON') or macro_defined(macros, '__ARM_NEON__')

    # ARMv5/v6 are too old for our armv7 target
    if level in (5, 6):
        return 'general-32'

    # ARMv7/v8 (and unknown levels) use armv7, upgraded to neon when present
    if level in (7, 8):
        return 'armv7-neon' if neon else 'armv7'

    return 'armv7-neon' if neon else 'general-32'

def detect_isa(cxx):

    try:
        macros = native_macros(cxx)
        arch   = get_arch(macros)

        if arch == 'x86':
            return detect_isa_x86(macros)

        if arch == 'ARM':
            return detect_isa_arm(macros)

    except:
        # Detection is best-effort; log the failure for the record and fall
        # back to 'Unknown' so a bad compiler probe never crashes the worker.
        print('Failed to detect ISA for compiler [%s]' % (cxx))
        traceback.print_exc()

    return 'Unknown'

if __name__ == '__main__':

    import sys

    cxx = sys.argv[1] if len(sys.argv) > 1 else 'g++'
    print(detect_isa(cxx))
