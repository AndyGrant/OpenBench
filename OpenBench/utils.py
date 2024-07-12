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

import datetime
import hashlib
import json
import math
import os
import random
import re
import requests

from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.db.models import F
from django.http import FileResponse
from django.utils import timezone
from wsgiref.util import FileWrapper

from OpenSite.settings import MEDIA_ROOT

from OpenBench.config import OPENBENCH_CONFIG
from OpenBench.models import *
from OpenBench.stats import TrinomialSPRT, PentanomialSPRT


import OpenBench.views


class TimeControl(object):

    FIXED_NODES = 'FIXED-NODES' # N= or nodes=
    FIXED_DEPTH = 'FIXED-DEPTH' # D= or depth=
    FIXED_TIME  = 'FIXED-TIME'  # MT= or movetime=
    CYCLIC      = 'CYCLIC'      # X/Y or X/Y+Z
    FISCHER     = 'FISCHER'     # Y or Y+Z

    @staticmethod
    def parse(time_str):

        # Display Nodes as N=, Depth as D=, MoveTime as MT=
        conversion = {
            'N'  :  'N', 'nodes'    :  'N',
            'D'  :  'D', 'depth'    :  'D',
            'MT' : 'MT', 'movetime' : 'MT',
        }

        # Searching for "nodes=", "depth=", and "movetime=" time controls
        pattern = r'(?P<mode>((N)|(D)|(MT)|(nodes)|(depth)|(movetime)))=(?P<value>(\d+))'
        if results := re.search(pattern, time_str.upper()):
            mode, value = results.group('mode', 'value')
            return '%s=%s' % (conversion[mode], value)

        # Searching for "X/Y+Z" time controls, where "X/" is optional
        pattern = r'(?P<moves>(\d+/)?)(?P<base>\d*(\.\d+)?)(?P<inc>\+(\d+\.)?\d+)?'
        if results := re.search(pattern, time_str):
            moves, base, inc = results.group('moves', 'base', 'inc')

            # Strip the trailing and leading symbols
            moves = None if moves == '' else moves.rstrip('/')
            inc   = 0.0  if inc   is None else inc.lstrip('+')

            # Format the time control for cutechess cleanly
            if moves is None: return '%.1f+%.2f' % (float(base), float(inc))
            return '%d/%.1f+%.2f' % (int(moves), float(base), float(inc))

        print ('FAIL')
        import sys
        sys.stdout.flush()

        raise Exception('Unable to parse Time Control (%s)' % (time_str))

    @staticmethod
    def control_type(time_str):

        # Return one of the types defined at the top of TimeControl

        if time_str.startswith('N='):
            return TimeControl.FIXED_NODES

        if time_str.startswith('D='):
            return TimeControl.FIXED_DEPTH

        if time_str.startswith('MT='):
            return TimeControl.FIXED_TIME

        if '/' in time_str:
            return TimeControl.CYCLIC

        return TimeControl.FISCHER

    @staticmethod
    def control_base(time_str):

        # Fixed-nodes, Fixed-depth, Fixed-time
        if '=' in time_str:
            return int(time_str.split('=')[1])

        # Cyclic
        if '/' in time_str:
            return float(time_str.split('/')[0])

        # Fischer or Sudden Death otherwise
        return float(time_str.split('+')[0])



def read_git_credentials(engine):
    fname = 'Config/credentials.%s' % (engine.replace(' ', '').lower())
    if os.path.exists(fname):
        with open(fname) as fin:
            return { 'Authorization' : 'token %s' % fin.readlines()[0].rstrip() }

def path_join(*args):
    return "/".join([f.lstrip("/").rstrip("/") for f in args]).rstrip('/')

def extract_option(options, option):

    match = re.search(r'(?<={0}=")[^"]*'.format(option), options)
    if match: return match.group()

    match = re.search(r'(?<={0}=\')[^\']*'.format(option), options)
    if match: return match.group()

    match = re.search(r'(?<={0}=)[^ ]*'.format(option), options)
    if match: return match.group()




def get_pending_tests():
    t = Test.objects.filter(approved=False)
    t = t.exclude(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-creation')

def get_active_tests():
    t = Test.objects.filter(approved=True)
    t = t.exclude(awaiting=True)
    t = t.exclude(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-priority', '-currentllr')

def get_completed_tests():
    t = Test.objects.filter(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-updated')

def get_awaiting_tests():
    t = Test.objects.filter(awaiting=True)
    t = t.exclude(finished=True)
    t = t.exclude(deleted=True)
    return t.order_by('-creation')


def getRecentMachines(minutes=5):
    target = datetime.datetime.utcnow()
    target = target.replace(tzinfo=timezone.utc)
    target = target - datetime.timedelta(minutes=minutes)
    return Machine.objects.filter(updated__gte=target)

def getMachineStatus(username=None):

    machines = getRecentMachines()

    if username != None:
        machines = machines.filter(user__username=username)

    return ": {0} Machines / ".format(len(machines)) + \
           "{0} Threads / ".format(sum([f.info['concurrency'] for f in machines])) + \
           "{0} MNPS ".format(round(sum([f.info['concurrency'] * f.mnps for f in machines]), 2))

def getPaging(content, page, url, pagelen=25):

    start = max(0, pagelen * (page - 1))
    end   = min(content.count(), pagelen * page)
    count = 1 + math.ceil(content.count() / pagelen)

    part1 = list(range(1, min(4, count)))
    part2 = list(range(page - 2, page + 1))
    part3 = list(range(page + 1, page + 3))
    part4 = list(range(count - 3, count + 1))

    pages = part1 + part2 + part3 + part4
    pages = [f for f in pages if f >= 1 and f <= count]
    pages = list(set(pages))
    pages.sort()

    final = []
    for f in range(len(pages) - 1):
        final.append(pages[f])
        if pages[f] != pages[f+1] - 1:
            final.append('...')

    context = {
        "url" : url, "page" : page, "pages" : final,
        "prev" : max(1, page - 1), "next" : max(1, min(page + 1, count - 1)),
    }

    return start, end, context



def branch_is_out_of_date(test):

    # Cannot compare across engines
    if test.dev_engine != test.base_engine:
        return False

    # Format the request to the Github endpoint
    base = 'https://api.github.com/repos/'
    base = test.dev_repo.replace('github.com', 'api.github.com/repos')
    url  = path_join(base, 'compare', '%s...%s' % (test.dev.sha, test.base.sha))

    try:
        # Out of date if ahead_by is non-zero
        headers = read_git_credentials(test.dev_engine)
        data    = requests.get(url, headers=headers).json()
        return data.get('ahead_by', 0) > 0

    except:
        # If something went wrong, just ignore it
        import traceback
        traceback.print_exc()
        return False



def get_machine(machineid, user, info):

    # Create a new machine if we don't have an id
    if machineid == 'None':
        return Machine(user=user, info=info)

    # Fetch the requested machine, which hopefully exists
    try: machine = Machine.objects.get(id=int(machineid))
    except: return None

    # Workload requests should always contain a MAC
    if 'mac_address' not in machine.info:
        return None

    # Soft-verify by checking if the MAC addresses match
    if machine.info['mac_address'] != info['mac_address']:
        return None

    return machine


# Purely Helper functions for Networks views

def network_disambiguate(engine, identifier):

    candidates = Network.objects.filter(engine=engine)

    # Identifier actually refers to the Network name
    if (network := candidates.filter(name=identifier).first()):
        return network

    # Identifier actually refers to the Network SHA
    if (network := candidates.filter(sha256=identifier).first()):
        return network

    # No Network exists with engine this Name or Sha
    return None

def network_upload(request, engine, name):

    # Extract and process the Network file to produce a SHA
    netfile = request.FILES['netfile']
    sha256  = hashlib.sha256(netfile.file.read()).hexdigest()[:8].upper()

    # Rejecct Networks with strange characters
    if not re.match(r'^[a-zA-Z0-9_.-]+$', name):
        return OpenBench.views.redirect(request, '/networks/', error='Valid characters are [a-zA-Z0-9_.-]')

    # Don't allow duplicate uploads for the same engine
    if Network.objects.filter(engine=engine, sha256=sha256):
        return OpenBench.views.redirect(request, '/networks/', error='Network with that hash already exists for that engine')

    # Don't allow duplicate uploads for the same engine
    if Network.objects.filter(engine=engine, name=name):
        return OpenBench.views.redirect(request, '/networks/', error='Network with that name already exists for that engine')

    # Filter out anyone who has used an unknown engine
    if engine not in OPENBENCH_CONFIG['engines'].keys():
        return OpenBench.views.redirect(request, '/networks/', error='No Engine found with matching name')

    # Save the file locally into /Media/ if we don't already have this file
    if not Network.objects.filter(sha256=sha256):
        FileSystemStorage().save('%s' % (sha256), netfile)

    # Create the Network object mapping to the saved local file
    Network.objects.create(
        sha256=sha256, name=name,
        engine=engine, author=request.user.username)

    # Redirect to Engine specific view, to add clarity
    return OpenBench.views.redirect(request, '/networks/%s/' % (engine), status='Uploaded %s for %s' % (name, engine))

def network_default(request, engine, network):

    # Update default to False for all Networks, except this one
    Network.objects.filter(engine=engine, default=True).update(default=False, was_default=True)
    network.default = network.was_default = True; network.save()

    # Report this, and refer to the Engine specific view
    status = 'Set %s as default for %s' % (network.name, network.engine)
    return OpenBench.views.redirect(request, '/networks/%s/' % (network.engine), status=status)

def network_delete(request, engine, network):

    # Don't allow deletion of important networks
    if network.default or network.was_default:
        error = 'You may not delete Default, or previous Default networks.'
        return OpenBench.views.redirect(request, '/networks/%s/' % (engine), error=error)

    # Save information before deleting the Network Model
    status = 'Deleted %s for %s' % (network.name, network.engine)
    sha256 = network.sha256; network.delete()

    # Only delete the actual file if no other engines use it
    if not Network.objects.filter(sha256=sha256):
        FileSystemStorage().delete(sha256)

    # Report this, and refer to the Engine specific view
    return OpenBench.views.redirect(request, '/networks/%s/' % (engine), status=status)

def network_download(request, engine, network):

    # Craft the download HTML response
    netfile  = os.path.join(MEDIA_ROOT, network.sha256)
    fwrapper = FileWrapper(open(netfile, 'rb'), 8192)
    response = FileResponse(fwrapper, content_type='application/octet-stream')

    # Set all headers and return response
    response['Expires'] = (datetime.datetime.utcnow() + datetime.timedelta(days=7)).ctime()
    response['Content-Length'] = os.path.getsize(netfile)
    response['Content-Disposition'] = 'attachment; filename=' + network.sha256
    return response

def network_edit(request, engine, network):

    if request.method == 'GET':
        return OpenBench.views.render(request, 'network.html', { 'network' : network })

    new_name        = request.POST['name']
    new_default     = request.POST['default'] == 'TRUE'
    new_was_default = request.POST['was_default'] == 'TRUE'

    # Reject new names that are already in use for this particular engine
    if new_name != network.name and Network.objects.filter(engine=network.engine, name=new_name):
        error = 'A Network already exists with the name %s for the %s engine' % (new_name, network.engine)
        return OpenBench.views.redirect(request, '/networks/%s/EDIT/%s' % (network.engine, network.sha256), error=error)

    # Rejecct new names with strange characters
    if not re.match(r'^[a-zA-Z0-9_.-]+$', new_name):
        return OpenBench.views.redirect(request, '/networks/', error='Valid characters are [a-zA-Z0-9_.-]')

    # Ensure all changes are made, or no changes are made
    with transaction.atomic():

        # Swap any references in tests, which use dev_netname and base_netname
        if new_name != network.name:
            Test.objects.filter(dev_engine=network.engine, dev_netname=network.name).update(dev_netname=new_name)
            Test.objects.filter(base_engine=network.engine, base_netname=network.name).update(base_netname=new_name)

        # Swap any current default Networks to a previous default
        if new_default:
            Network.objects.filter(engine=engine, default=True).update(default=False, was_default=True)

        # Update the actual Network. Ensure was_default is set if default is
        network.name        = new_name
        network.default     = new_default
        network.was_default = new_default or new_was_default
        network.save()

    return OpenBench.views.redirect(request, '/networks/%s' % (network.engine), status='Applied changes')


def update_test(request, machine):

    # Extract error information
    crashes    = int(request.POST['crashes'   ])
    timelosses = int(request.POST['timelosses'])
    illegals   = int(request.POST['illegals'  ])

    # Extract Database information
    machine_id = int(request.POST['machine_id'])
    result_id  = int(request.POST['result_id' ])
    test_id    = int(request.POST['test_id'   ])

    # Trinomial Implementation
    losses, draws, wins = map(int, request.POST['trinomial'].split())
    games = losses + draws + wins

    # Pentanomial Implementation
    LL, LD, DD, DW, WW = map(int, request.POST['pentanomial'].split())

    with transaction.atomic():

        test = Test.objects.select_for_update().get(id=test_id)

        if test.finished or test.deleted:
            return { 'stop' : True }

        test.losses += losses # Trinomial
        test.draws  += draws
        test.wins   += wins
        test.LL     += LL     # Pentanomial
        test.LD     += LD
        test.DD     += DD
        test.DW     += DW
        test.WW     += WW
        test.games  += games  # Overall

        # Consider only Crashes or Illegal moves as real errors
        test.error = bool(test.error or crashes or illegals)

        if test.test_mode == 'SPRT':

            # Compute a new LLR for the updated results ( Penta )
            if test.use_penta:
                results = (test.LL, test.LD, test.DD, test.DW, test.WW)
                test.currentllr = PentanomialSPRT(results, test.elolower, test.eloupper)

            # Compute a new LLR for the updated results ( Tri )
            elif test.use_tri:
                results = (test.losses, test.draws, test.wins)
                test.currentllr = TrinomialSPRT(results, test.elolower, test.eloupper)

            # Check for H0 or H1 being accepted
            test.passed   = test.currentllr > test.upperllr
            test.failed   = test.currentllr < test.lowerllr
            test.finished = test.passed or test.failed

        elif test.test_mode == 'GAMES':

            # Finish test once we've played the proper amount of games
            test.passed   = test.games >= test.max_games and test.wins >= test.losses
            test.failed   = test.games >= test.max_games and test.wins <  test.losses
            test.finished = test.passed or test.failed

        elif test.test_mode == 'SPSA':

            # Update each parameter, as determined by the Worker
            for name, param in test.spsa['parameters'].items():
                x = param['value'] + float(request.POST['spsa_%s' % (name)])
                param['value'] = max(param['min'], min(param['max'], x))

            test.finished = test.games >= 2 * test.spsa['pairs_per'] * test.spsa['iterations']

        elif test.test_mode == 'DATAGEN':

            # Finished, and always passing, for a completed DATAGEN Workload
            test.passed = test.finished = test.games >= test.max_games

        test.save()

    # Update Result object; No risk from concurrent access
    Result.objects.filter(id=result_id).update(
        games    = F('games'   ) + games,
        losses   = F('losses'  ) + losses,
        draws    = F('draws'   ) + draws,
        wins     = F('wins'    ) + wins,
        LL       = F('LL'      ) + LL,
        LD       = F('LD'      ) + LD,
        DD       = F('DD'      ) + DD,
        DW       = F('DW'      ) + DW,
        WW       = F('WW'      ) + WW,
        crashes  = F('crashes' ) + crashes,
        timeloss = F('timeloss') + timelosses,
        updated  = timezone.now()
    )

    # Update Profile object; No risk from concurrent access
    Profile.objects.filter(user=Machine.objects.get(id=machine_id).user).update(
        games=F('games') + games,
        updated=timezone.now()
    )

    # Update Machine object; No risk from concurrent access
    Machine.objects.filter(id=machine_id).update(
        updated=timezone.now()
    )

    return [{}, { 'stop' : True }][test.finished]
