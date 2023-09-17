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

# Module serves a singular purpose, to invoke: get_workload(Machine)
#
# Selects a Test, from the active tests, with the following procedure...
#   1. Remove all tests with Engines not supported by the Worker
#   2. Remove all tests with unmet Syzygy requirements
#   3. Remove all tests with thread-odds, if the Worker is hyperthreading
#   4. Remove all tests where our machine will exceed the Worker Limit
#   5. Remove all tests where our machine will exceed the Thread Limit
#   6. Remove all tests that don't have the highest priority in the test list
#
# At this point, we select from these candidate tests using the following:
#   1. Randomly select from any tests that have 0 workers
#   2. Repeat the same test ( if it exists ), if distribution is still "Fair"
#   3. Select the test with the most "Unfair" distribution of workers
#
# Our response includes three critical values:
#
#   1. cutechess-count      The # of Sockets on the worker for SPRT/FIXED tests
#                           The # of max possible concurrent games for SPRT tests
#   2. concurrency-per      The # of concurrent games to run per Cutechess copy.
#                           Function of the machine, and each engine's options
#   3. games-per-cutechess  # of total games to run per Cutechess copy
#                           This is the workload_size times concurrency-per

import math
import random
import re
import sys

import OpenBench.utils

from OpenBench.config import OPENBENCH_CONFIG
from OpenBench.models import Result, Test

def get_workload(machine):

    # Select a workload from the possible ones, if we can
    if not (test := select_workload(machine)):
        return {}

    # Fetch or create the Result object for the test
    try: result = Result.objects.get(test=test, machine=machine)
    except: result = Result(test=test, machine=machine)

    # Update the Machine's status and save everything
    machine.workload = test.id; machine.save(); result.save()
    return { 'workload' : workload_to_dictionary(test, result, machine) }

def select_workload(machine):

    # Find valid workloads, given the current distribution of workers
    active, distribution = worker_distribution(machine)
    if not (tests := filter_valid_workloads(active, machine, distribution)):
        return {}

    # Find the tests most deserving of resources currently
    ratios = [distribution[x.id]['threads'] / x.throughput for x in tests]
    lowest_indices = [i for i, r in enumerate(ratios) if r == min(ratios)]

    # Machine is out of date; or there is an unassigned test
    if machine.workload not in distribution or min(ratios) == 0:
        return tests[random.choice(lowest_indices)]

    # Determine the "fair" ratio given the total threads and total throughput of tests
    total_threads    = sum([distribution[x.id]['threads'] for x in tests])
    total_throughput = sum([x.throughput for x in tests])
    fair_ratio       = total_threads / total_throughput

    # Repeat the same test if the distribution is still fair
    if min(ratios) / fair_ratio > 0.75:
        return Test.objects.get(id=machine.workload)

    # Fallback to simply doing the least attention given test
    return tests[random.choice(lowest_indices)]

def worker_distribution(machine):

    # For each test ( which some worker claims to be running ), return
    # a dict with the # of workers and # of threads actively on the test

    tests = OpenBench.utils.get_active_tests()

    distribution = {
        test.id : { 'workers' : 0, 'threads' : 0 } for test in tests
    }

    # Don't count ourselves; and don't include non-active tests
    for x in OpenBench.utils.getRecentMachines():
        if machine != x and x.workload in distribution:
            distribution[x.workload]['workers'] += 1
            distribution[x.workload]['threads'] += x.info['concurrency']

    return tests, distribution

def filter_valid_workloads(tests, machine, distribution):

    # Skip engines that the Machine cannot handle
    for engine in OPENBENCH_CONFIG['engines'].keys():
        if engine not in machine.info['supported']:
            tests = tests.exclude(dev_engine=engine)
            tests = tests.exclude(base_engine=engine)

    # Skip tests with unmet Syzygy requirements
    for K in range(machine.info['syzygy_max'] + 1, 10):
        tests = tests.exclude(syzygy_adj='%d-MAN' % (K))
        tests = tests.exclude(syzygy_wdl='%d-MAN' % (K))

    # Skip tests that would waste available Threads or exceed them
    threads      = machine.info['concurrency']
    sockets      = machine.info['sockets']
    hyperthreads = machine.info['physical_cores'] < threads
    options = [x for x in tests if valid_assignment(machine, x, distribution)]

    # Finally refine for tests of the highest priority
    if not options: return []
    highest_prio = max(options, key=lambda x: x.priority).priority
    return [test for test in options if test.priority == highest_prio]

def valid_assignment(machine, test, distribution):

    # Extract thread requirements from the test itself
    dev_threads  = int(OpenBench.utils.extract_option(test.dev_options,  'Threads'))
    base_threads = int(OpenBench.utils.extract_option(test.base_options, 'Threads'))

    # Extract the information from our machine
    threads      = machine.info['concurrency']
    sockets      = machine.info['sockets']
    hyperthreads = machine.info['physical_cores'] < threads

    # SPSA plays a pair at a time, not a game at a time
    is_spsa = test.test_mode == 'SPSA'
    is_sprt = test.test_mode != 'SPSA'

    # Refuse if there are not enough threads-per-socket for the test
    if (1 + is_spsa) * max(dev_threads, base_threads) > (threads / sockets):
        return False

    # Refuse thread odds if we are using hyperthreads
    if dev_threads != base_threads and hyperthreads:
        return False

    # Refuse to assign more workers than the test will allow
    current_workers = distribution[test.id]['workers'] if test.id in distribution else 0
    if test.worker_limit and current_workers >= test.worker_limit:
        return False

    # Refuse to assign more threads than the test will allow
    current_threads = distribution[test.id]['threads'] if test.id in distribution else 0
    if test.thread_limit and current_threads + threads > test.thread_limit:
        return False

    # All Criteria have been met
    return True


def workload_to_dictionary(test, result, machine):

    workload = {}

    workload['result'] = {
        'id'  : result.id,
    }

    workload['test'] = {
        'id'            : test.id,
        'type'          : test.test_mode,
        'syzygy_wdl'    : test.syzygy_wdl,
        'syzygy_adj'    : test.syzygy_adj,
        'win_adj'       : test.win_adj,
        'draw_adj'      : test.draw_adj,
        'workload_size' : test.workload_size,
        'book'          : OPENBENCH_CONFIG['books'][test.book_name],
    }

    workload['test']['dev'] = {
        'id'           : test.dev.id,
        'name'         : test.dev.name,
        'source'       : test.dev.source,
        'sha'          : test.dev.sha,
        'bench'        : test.dev.bench,
        'engine'       : test.dev_engine,
        'options'      : test.dev_options,
        'network'      : test.dev_network,
        'time_control' : test.dev_time_control,
        'nps'          : OPENBENCH_CONFIG['engines'][test.dev_engine]['nps'],
        'build'        : OPENBENCH_CONFIG['engines'][test.dev_engine]['build'],
        'private'      : OPENBENCH_CONFIG['engines'][test.dev_engine]['private'],
    }

    workload['test']['base'] = {
        'id'           : test.base.id,
        'name'         : test.base.name,
        'source'       : test.base.source,
        'sha'          : test.base.sha,
        'bench'        : test.base.bench,
        'engine'       : test.base_engine,
        'options'      : test.base_options,
        'network'      : test.base_network,
        'time_control' : test.base_time_control,
        'nps'          : OPENBENCH_CONFIG['engines'][test.base_engine]['nps'],
        'build'        : OPENBENCH_CONFIG['engines'][test.base_engine]['build'],
        'private'      : OPENBENCH_CONFIG['engines'][test.base_engine]['private'],
    }

    workload['allocation'] = game_allocation(test, machine)
    workload['spsa']       = spsa_to_dictionary(test, workload['allocation']['cutechess-count'])

    return workload

def spsa_to_dictionary(test, permutations):

    if test.test_mode != 'SPSA':
        return None

    # C & R are scaled over the course of the iterations
    iteration     = 1 + (test.games / (test.spsa['pairs_per'] * 2))
    c_compression = iteration ** test.spsa['Gamma']
    r_compression = (test.spsa['A'] + iteration) ** test.spsa['Alpha']

    spsa = {}
    for name, param in test.spsa['parameters'].items():

        spsa[name] = {
            'white' : [], # One for each Permutation the Worker will run
            'black' : [], # One for each Permutation the Worker will run
            'flip'  : [], # One for each Permutation the Worker will run
        }

        # C & R are constants for a particular assignment, for all Permutations
        spsa[name]['c'] = param['c'] / c_compression
        spsa[name]['r'] = param['a'] / r_compression / spsa[name]['c'] ** 2

        for f in range(permutations):

            # Adjust current best by +- C
            flip = 1 if random.getrandbits(1) else -1
            white = param['value'] + flip * spsa[name]['c']
            black = param['value'] - flip * spsa[name]['c']

            # Probabilistic rounding for integer types
            if not param['float']:
                white = math.floor(white + random.uniform(0, 1))
                black = math.floor(black + random.uniform(0, 1))

            # Clip within [Min, Max]
            white = max(param['min'], min(param['max'], white))
            black = max(param['min'], min(param['max'], black))

            # Round integer values down
            if not param['float']:
                white = int(white)
                black = int(black)

            # Append each permutation
            spsa[name]['white'].append(white)
            spsa[name]['black'].append(black)
            spsa[name]['flip' ].append(flip)

    return spsa


def extract_option(options, option):

    if (match := re.search('(?<=%s=")[^"]*' % (option), options)):
        return match.group()

    if (match := re.search('(?<=%s=\')[^\']*' % (option), options)):
        return match.group()

    if (match := re.search('(?<=%s=)[^ ]*' % (option), options)):
        return match.group()

def game_allocation(test, machine):

    # Every Option contains Threads= for both engines
    dev_threads  = int(extract_option(test.dev_options, 'Threads'))
    base_threads = int(extract_option(test.base_options, 'Threads'))

    # "concurrency" is the total number of connected Threads
    worker_threads = machine.info['concurrency']
    worker_sockets = machine.info['sockets']

    # Concurrency per cutechess, if splitting by sockets
    concurrency = (worker_threads // worker_sockets) // max(dev_threads, base_threads)

    # Number of params being evaluated at a single time
    spsa_count = (worker_threads // max(dev_threads, base_threads)) // 2

    is_spsa = test.test_mode == 'SPSA'

    return {
        'cutechess-count'     : spsa_count if is_spsa else worker_sockets,
        'concurrency-per'     : 1 if is_spsa else concurrency,
        'games-per-cutechess' : 2 * test.workload_size * (1 if is_spsa else concurrency),
    }
