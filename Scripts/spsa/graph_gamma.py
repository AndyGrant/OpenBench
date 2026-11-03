#!/usr/bin/env python3

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

# Visualize how SPSA's C value decays over the lifetime of a tune, for a
# range of Gamma values. This mirrors the scaling done when assigning a
# workload (see OpenBench/spsa_utils.py):
#
#     c_value       = c_end * iterations ** gamma      # stored on creation
#     iteration     = 1 + games / (pairs_per * 2)      # 1 .. iterations + 1
#     c_compression = iteration ** gamma
#     c             = c_value / c_compression
#
# Substituting a hypothetical parameter with c_end == 1, the effective C at
# a completion fraction p (where iteration = 1 + p * iterations) reduces to:
#
#     c(p) = (iterations / (1 + p * iterations)) ** gamma
#
# So C begins at iterations ** gamma and decays toward c_end == 1 as the tune
# completes. Larger Gamma means a steeper, more aggressive decay.

import argparse

import numpy as np
import matplotlib.pyplot as plt

# Base Gamma, then progressively gentler decays by dividing it down
BASE_GAMMA = 0.101
DIVISORS   = [1, 2, 5, 10, 25]

def c_schedule(fractions, gamma, iterations, c_end=1.0):

    # Effective C value across a tune for a param with the given c_end.
    # Mirrors c_value / c_compression from spsa_utils.py.

    c_value       = c_end * iterations ** gamma
    iteration     = 1 + fractions * iterations
    c_compression = iteration ** gamma

    return c_value / c_compression

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Plot SPSA C decay for a range of Gamma values')
    parser.add_argument('--output'    , default='gamma.png', help='Output image path (default: gamma.png)')
    parser.add_argument('--iterations', default=30000, type=int, help='Total SPSA iterations (default: 30000)')
    parser.add_argument('--c-end'     , default=1.0, type=float, help='Hypothetical parameter c_end (default: 1.0)')
    parser.add_argument('--end'       , default=1.0, type=float, help='Graph only up to this completion fraction (default: 1.0)')
    args = parser.parse_args()

    fractions = np.linspace(0.0, args.end, 1000)

    fig, ax = plt.subplots(figsize=(10, 6))

    for divisor in DIVISORS:
        gamma = BASE_GAMMA / divisor
        label = 'Gamma = %.5f' % (gamma) if divisor == 1 else 'Gamma = %.5f (%.3f / %d)' % (gamma, BASE_GAMMA, divisor)
        ax.plot(fractions * 100, c_schedule(fractions, gamma, args.iterations, args.c_end), label=label, linewidth=2)

    ax.set_title('SPSA C Decay by Gamma (iterations = %d, c_end = %g)' % (args.iterations, args.c_end))
    ax.set_xlabel('Tune Completion (%)')
    ax.set_ylabel('Effective C Value')
    ax.set_xlim(0, args.end * 100)
    ax.grid(True, alpha=0.3)
    ax.legend()

    fig.tight_layout()
    fig.savefig(args.output, dpi=150)
    print('Saved plot to %s' % (args.output))
