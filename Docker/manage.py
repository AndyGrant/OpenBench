#!/usr/bin/env python3

# Spawn/kill pinned OpenBench worker containers. Detects the machine's CPU
# topology (physical cores, SMT siblings, NUMA nodes) from /sys, then
# partitions it into --count workers of --threads logical threads each,
# keeping each worker's cores within a single NUMA node where possible.
# Use the 'plan' action to preview the assignment without starting anything.

import argparse
import os
import re
import subprocess
import sys

IMAGE       = 'openbench-client'
CPU_SYS_DIR = '/sys/devices/system/cpu'

def read_int(path):
    with open(path) as f:
        return int(f.read().strip())

def online_cpus():

    cpus = []
    for entry in os.listdir(CPU_SYS_DIR):
        if not (m := re.fullmatch(r'cpu(\d+)', entry)):
            continue
        online_file = os.path.join(CPU_SYS_DIR, entry, 'online')
        if os.path.exists(online_file) and read_int(online_file) == 0:
            continue
        cpus.append(int(m.group(1)))
    return sorted(cpus)

def node_of(cpu):

    # NUMA node is exposed as a symlink named nodeN inside the cpu's sysfs dir
    cpu_dir = os.path.join(CPU_SYS_DIR, 'cpu%d' % (cpu))
    for entry in os.listdir(cpu_dir):
        if m := re.fullmatch(r'node(\d+)', entry):
            return int(m.group(1))
    return 0

def discover_topology():

    # Group logical cpus by (package_id, core_id), which naturally clusters
    # SMT siblings together regardless of how the kernel numbers them.
    cores = {}
    for cpu in online_cpus():
        topo       = os.path.join(CPU_SYS_DIR, 'cpu%d' % (cpu), 'topology')
        package_id = read_int(os.path.join(topo, 'physical_package_id'))
        core_id    = read_int(os.path.join(topo, 'core_id'))
        cores.setdefault((package_id, core_id), set()).add(cpu)

    sizes = {len(siblings) for siblings in cores.values()}
    if len(sizes) != 1:
        sys.exit('error: inconsistent SMT width across cores: %s' % (sorted(sizes)))
    threads_per_core = sizes.pop()

    # physical_cores is a list of (node_id, sorted_logical_cpus), one entry
    # per physical core, ordered by node then core id
    physical_cores = [(node_of(min(siblings)), key, sorted(siblings)) for key, siblings in cores.items()]
    physical_cores.sort(key=lambda item: (item[0], item[1]))
    return [(node, cpus) for node, _, cpus in physical_cores], threads_per_core

def format_ranges(nums):

    nums   = sorted(nums)
    ranges = []
    start = prev = nums[0]

    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append((start, prev))
        start = prev = n
    ranges.append((start, prev))

    return ','.join('%d-%d' % (a, b) if a != b else '%d' % (a) for a, b in ranges)

def plan_groups(threads, count):

    physical_cores, threads_per_core = discover_topology()
    total_logical = sum(len(cpus) for _, cpus in physical_cores)

    if threads % threads_per_core != 0:
        sys.exit('error: --threads must be a multiple of %d (this machine has %d-way SMT)'
                  % (threads_per_core, threads_per_core))

    if threads * count > total_logical:
        sys.exit('error: %d workers x %d threads = %d exceeds %d logical threads on this machine'
                  % (count, threads, threads * count, total_logical))

    cores_per_worker = threads // threads_per_core
    if cores_per_worker * count > len(physical_cores):
        sys.exit('error: %d workers need %d physical cores each (%d total), only %d available'
                  % (count, cores_per_worker, cores_per_worker * count, len(physical_cores)))

    groups = []
    for i in range(count):
        chunk = physical_cores[i * cores_per_worker : (i + 1) * cores_per_worker]
        cpus  = sorted(cpu for _, siblings in chunk for cpu in siblings)
        nodes = sorted({node for node, _ in chunk})
        groups.append((cpus, nodes))

    return groups, threads_per_core, total_logical

def label(i, count):
    return chr(ord('A') + i) if count <= 26 else '%02d' % (i)

def show_plan(threads, count):

    groups, threads_per_core, total_logical = plan_groups(threads, count)
    print('detected %d logical threads, %d-way SMT' % (total_logical, threads_per_core))

    for i, (cpus, nodes) in enumerate(groups):
        print('  worker %s: cpus %s  mems %s'
              % (label(i, count), format_ranges(cpus), ','.join(map(str, nodes))))

def require_env(name):
    if not (value := os.environ.get(name)):
        sys.exit('error: environment variable %s must be set' % (name))
    return value

def spawn(threads, count, prefix, creds):

    user     = require_env('OB_USER')
    password = require_env('OB_PASS')
    server   = require_env('OB_SERVER')
    if creds:
        creds = os.path.abspath(creds)
        if not os.path.isdir(creds):
            sys.exit('error: --creds directory not found: %s' % (creds))

    groups, *_ = plan_groups(threads, count)

    # Leave one thread per worker for the container/OS itself; the client
    # only gets to use the rest for search
    client_threads = threads - 1

    for i, (cpus, nodes) in enumerate(groups):

        lbl    = label(i, count)
        name   = '%s-%s' % (IMAGE, lbl)
        cpuset = format_ranges(cpus)
        mems   = ','.join(map(str, nodes))

        cmd = [
            'docker', 'run', '-d',
            '--name', name,
            '--cpuset-cpus', cpuset,
            '--cpuset-mems', mems,
            *(['-v', '%s:/home/worker/credentials:ro' % (creds)] if creds else []),
            '-e', 'OB_USER=%s'     % (user),
            '-e', 'OB_PASS=%s'     % (password),
            '-e', 'OB_SERVER=%s'   % (server),
            '-e', 'OB_IDENTITY=%s-%s' % (prefix, lbl),
            '-e', 'OB_THREADS=%d'  % (client_threads),
            IMAGE,
        ]

        print('starting %s (cpus %s, mems %s)' % (name, cpuset, mems))
        subprocess.run(cmd, check=True)

def kill():
    ids = subprocess.run(
        ['docker', 'ps', '-aq', '--filter', 'ancestor=%s' % (IMAGE)],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    if ids:
        subprocess.run(['docker', 'rm', '-f', *ids], check=False)

def list_workers():
    subprocess.run([
        'docker', 'ps', '-a',
        '--filter', 'ancestor=%s' % (IMAGE),
        '--format', 'table {{.Names}}\t{{.Status}}\t{{.RunningFor}}',
    ], check=False)

def main():

    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['spawn', 'kill', 'list', 'plan'])
    p.add_argument('--threads', type=int, help='logical threads per worker, incl. SMT siblings (required for spawn/plan)')
    p.add_argument('--count', type=int, help='number of workers (required for spawn/plan)')
    p.add_argument('--prefix', help='instance name prefix, e.g. gpu101 -> gpu101-A (required for spawn)')
    p.add_argument('--creds', help='optional dir of credentials.<engine> files, bind-mounted read-only')
    args = p.parse_args()

    if args.action in ('spawn', 'plan') and (args.threads is None or args.count is None):
        sys.exit('error: --threads and --count must be provided for %s' % (args.action))

    if args.action == 'spawn' and not args.prefix:
        sys.exit('error: --prefix must be provided for spawn')

    if args.action == 'spawn':
        spawn(args.threads, args.count, args.prefix, args.creds)
    elif args.action == 'kill':
        kill()
    elif args.action == 'plan':
        show_plan(args.threads, args.count)
    else:
        list_workers()

if __name__ == '__main__':
    main()
