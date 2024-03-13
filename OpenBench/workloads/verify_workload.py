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

# Module serves a singular purpose, to invoke:
# >>> verify_workload(request, type)
#
# Given a request, and a workload_type [TEST, TUNE, DATAGEN], verify all of
# the form inputs, collect all of the information from Github, verify all of
# the data from Github, and return a tuple of (errors, engines)
#
# For Verifying and Collection information on a Test:
#   >>> errors, engine_info = verify_workload(request, 'TEST')
#   >>> dev_info, base_info = engine_info
#
# For Verifying and Collection information on a Tune:
#   >>> errors, engine_info = verify_workload(request, 'TUNE')
#
# For Verifying and Collection information on Datagen:
#   >>> errors, engine_info = verify_workload(request, 'DATAGEN')
#   >>> dev_info, base_info = engine_info

import os
import re
import requests
import traceback

import OpenBench.config
import OpenBench.utils

from OpenBench.models import *

def verify_workload(request, workload_type):

    assert workload_type in [ 'TEST', 'TUNE', 'DATAGEN' ]

    errors = []

    if workload_type == 'TEST':
        verify_test_creation(errors, request)
        dev  = collect_github_info(errors, request, 'dev')
        base = collect_github_info(errors, request, 'base')
        return errors, (dev, base)

    if workload_type == 'TUNE':
        verify_tune_creation(errors, request)
        engine = collect_github_info(errors, request, 'dev')
        return errors, engine

    if workload_type == 'DATAGEN':
        verify_datagen_creation(errors, request)
        dev  = collect_github_info(errors, request, 'dev')
        base = collect_github_info(errors, request, 'base')
        return errors, (dev, base)

def verify_test_creation(errors, request):

    verifications = [

        # Verify everything about the Dev Engine
        (verify_configuration  , 'dev_engine', 'Dev Engine', 'engines'),
        (verify_github_repo    , 'dev_repo'),
        (verify_network        , 'dev_network', 'Dev Network', 'dev_engine'),
        (verify_options        , 'dev_options', 'Threads', 'Dev Options'),
        (verify_options        , 'dev_options', 'Hash', 'Dev Options'),
        (verify_time_control   , 'dev_time_control', 'Dev Time Control'),

        # Verify everything about the Base Engine
        (verify_configuration  , 'base_engine', 'Base Engine', 'engines'),
        (verify_github_repo    , 'base_repo'),
        (verify_network        , 'base_network', 'Base Network', 'base_engine'),
        (verify_options        , 'base_options', 'Threads', 'Base Options'),
        (verify_options        , 'base_options', 'Hash', 'Base Options'),
        (verify_time_control   , 'base_time_control', 'Base Time Control'),

        # Verify everything about the Test Settings
        (verify_configuration  , 'book_name', 'Book', 'books'),
        (verify_upload_pgns    , 'upload_pgns', 'Upload PGNs'),
        (verify_test_mode      , 'test_mode'),
        (verify_sprt_bounds    , 'test_bounds'),
        (verify_sprt_conf      , 'test_confidence'),
        (verify_max_games      , 'test_max_games'),

        # Verify everything about the General Settings
        (verify_integer        , 'priority', 'Priority'),
        (verify_greater_than   , 'throughput', 'Throughput', 0),
        (verify_syzygy_field   , 'syzygy_wdl', 'Syzygy WDL'),

        # Verify everything about the Workload Settings
        (verify_integer        , 'workload_size', 'Workload Size'),
        (verify_greater_than   , 'workload_size', 'Workload Size', 0),

        # Verify everything about the Adjudicaton Settings
        (verify_syzygy_field   , 'syzygy_adj', 'Syzygy Adjudication'),
        (verify_win_adj        , 'win_adj'),
        (verify_draw_adj       , 'draw_adj'),
    ]

    for verification in verifications:
        verification[0](errors, request, *verification[1:])

def verify_tune_creation(errors, request):

    verifications = [

        # Verify the SPSA raw inputs and methods
        (verify_spsa_inputs           , 'spsa_inputs'),
        (verify_spsa_reporting_type   , 'spsa_reporting_type', 'Reporting Method'),
        (verify_spsa_distribution_type, 'spsa_distribution_type', 'Distribution Method'),

        # Verify everything about the Engine
        (verify_configuration         , 'dev_engine', 'Engine', 'engines'),
        (verify_github_repo           , 'dev_repo'),
        (verify_network               , 'dev_network', 'Network', 'dev_engine'),
        (verify_options               , 'dev_options', 'Threads', 'Options'),
        (verify_options               , 'dev_options', 'Hash', 'Options'),
        (verify_time_control          , 'dev_time_control', 'Time Control'),

        # Verify everything about the Test Settings
        (verify_configuration         , 'book_name', 'Book', 'books'),
        (verify_upload_pgns           , 'upload_pgns', 'Upload PGNs'),

        # Verify everything about the General Settings
        (verify_integer               , 'priority', 'Priority'),
        (verify_greater_than          , 'throughput', 'Throughput', 0),
        (verify_syzygy_field          , 'syzygy_wdl', 'Syzygy WDL'),

        # Verify everything about the Adjudicaton Settings
        (verify_syzygy_field          , 'syzygy_adj', 'Syzygy Adjudication'),
        (verify_win_adj               , 'win_adj'),
        (verify_draw_adj              , 'draw_adj'),

        # Verify everything about the SPSA Settings
        (verify_float                 , 'spsa_alpha', 'SPSA A-Ratio'),
        (verify_float                 , 'spsa_alpha', 'SPSA Alpha'),
        (verify_float                 , 'spsa_gamma', 'SPSA Gamma'),
        (verify_integer               , 'spsa_iterations', 'SPSA Iterations'),
        (verify_integer               , 'spsa_pairs_per', 'SPSA Pairs-Per'),
        (verify_greater_than          , 'spsa_alpha', 'SPSA A-Ratio', 0.00),
        (verify_greater_than          , 'spsa_alpha', 'SPSA Alpha', 0.00),
        (verify_greater_than          , 'spsa_gamma', 'SPSA Gamma', 0.00),
        (verify_greater_than          , 'spsa_iterations', 'SPSA Iterations', 0),
        (verify_greater_than          , 'spsa_pairs_per', 'SPSA Pairs-Per', 0),
    ]

    for verification in verifications:
        verification[0](errors, request, *verification[1:])

def verify_datagen_creation(errors, request):

    verifications = [

        # Verify everything about the Dev Engine
        (verify_configuration  , 'dev_engine', 'Dev Engine', 'engines'),
        (verify_github_repo    , 'dev_repo'),
        (verify_network        , 'dev_network', 'Dev Network', 'dev_engine'),
        (verify_options        , 'dev_options', 'Threads', 'Dev Options'),
        (verify_options        , 'dev_options', 'Hash', 'Dev Options'),
        (verify_time_control   , 'dev_time_control', 'Dev Time Control'),

        # Verify everything about the Base Engine
        (verify_configuration  , 'base_engine', 'Base Engine', 'engines'),
        (verify_github_repo    , 'base_repo'),
        (verify_network        , 'base_network', 'Base Network', 'base_engine'),
        (verify_options        , 'base_options', 'Threads', 'Base Options'),
        (verify_options        , 'base_options', 'Hash', 'Base Options'),
        (verify_time_control   , 'base_time_control', 'Base Time Control'),

        # Verify everything about the Datagen Settings
        (verify_datagen_games  , 'datagen_max_games'),
        (verify_datagen_genfens, 'datagen_custom_genfens'),
        (verify_datagen_reverse, 'datagen_play_reverses'),
        (verify_datagen_book   , 'book_name', 'Book', 'books'),
        (verify_upload_pgns    , 'upload_pgns', 'Upload PGNs'),

        # Verify everything about the General Settings
        (verify_integer        , 'priority', 'Priority'),
        (verify_greater_than   , 'throughput', 'Throughput', 0),
        (verify_syzygy_field   , 'syzygy_wdl', 'Syzygy WDL'),

        # Verify everything about the Workload Settings
        (verify_integer        , 'workload_size', 'Workload Size'),
        (verify_greater_than   , 'workload_size', 'Workload Size', 0),

        # Verify everything about the Adjudicaton Settings
        (verify_syzygy_field   , 'syzygy_adj', 'Syzygy Adjudication'),
        (verify_win_adj        , 'win_adj'),
        (verify_draw_adj       , 'draw_adj'),
    ]

    for verification in verifications:
        verification[0](errors, request, *verification[1:])


def verify_integer(errors, request, field, field_name):
    try: int(request.POST[field])
    except: errors.append('"{0}" is not an Integer'.format(field_name))

def verify_float(errors, request, field, field_name):
    try: float(request.POST[field])
    except: errors.append('"{0}" is not a Float'.format(field_name))

def verify_greater_than(errors, request, field, field_name, value):
    try: assert float(request.POST[field]) > value
    except: errors.append('"{0}" is not greater than {1}'.format(field_name, value))

def verify_options(errors, request, field, option, field_name):
    try: assert int(OpenBench.utils.extract_option(request.POST[field], option)) >= 1
    except: errors.append('"{0}" needs to be at least 1 for {1}'.format(option, field_name))

def verify_configuration(errors, request, field, field_name, parent):
    try: assert request.POST[field] in OpenBench.config.OPENBENCH_CONFIG[parent].keys()
    except: errors.append('{0} was not found in the configuration'.format(field_name))

def verify_time_control(errors, request, field, field_name):
    try: OpenBench.utils.TimeControl.parse(request.POST[field])
    except: errors.append('{0} is not parsable'.format(field_name))

def verify_win_adj(errors, request, field):
    try:
        if (content := request.POST[field]) == 'None': return
        assert re.match('movecount=[0-9]+ score=[0-9]+', content)
    except: errors.append('Invalid Win Adjudication Setting. Try "None"?')

def verify_draw_adj(errors, request, field):
    try:
        if (content := request.POST[field]) == 'None': return
        assert re.match('movenumber=[0-9]+ movecount=[0-9]+ score=[0-9]+', content)
    except: errors.append('Invalid Draw Adjudication Setting. Try "None"?')

def verify_github_repo(errors, request, field):
    pattern = r'^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+\/?$'
    try: assert re.match(pattern, request.POST[field])
    except: errors.append('Sources must be found on https://github.com/<User>/<Repo>')

def verify_network(errors, request, field, field_name, engine_field):
    try:
        if request.POST[field] == '': return
        Network.objects.get(engine=request.POST[engine_field], sha256=request.POST[field])
    except: errors.append('Unknown Network Provided for {0}'.format(field_name))

def verify_test_mode(errors, request, field):
    try: assert request.POST[field] in ['SPRT', 'GAMES']
    except: errors.append('Unknown Test Mode')

def verify_sprt_bounds(errors, request, field):
    try:
        if request.POST['test_mode'] != 'SPRT': return
        pattern = r'^\[(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\]$'
        match   = re.match(pattern, request.POST['test_bounds'])
        assert float(match.group(1)) < float(match.group(2))
    except: errors.append('SPRT Bounds must be formatted as [float1, float2]')

def verify_sprt_conf(errors, request, field):
    try:
        if request.POST['test_mode'] != 'SPRT': return
        pattern = r'^\[(-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?)\]$'
        match   = re.match(pattern, request.POST['test_confidence'])
        assert 0.00 < float(match.group(1)) < 1.00
        assert 0.00 < float(match.group(2)) < 1.00
    except: errors.append('Confidence Bounds must be formatted as [float1, float2], within (0.00, 1.00)')

def verify_max_games(errors, request, field):
    try:
        if request.POST['test_mode'] != 'GAMES': return
        assert int(request.POST['test_max_games']) > 0
    except: errors.append('Fixed Games Tests must last at least one game')

def verify_syzygy_field(errors, request, field, field_name):
    candidates = ['OPTIONAL', 'DISABLED', '3-MAN', '4-MAN', '5-MAN', '6-MAN', '7-MAN']
    try: assert request.POST[field] in candidates
    except: errors.append('%s must be in %s' % (field_name, ', '.join(candidates)))

def verify_spsa_inputs(errors, request, field):

    try:

        if not (lines := request.POST[field].split('\n')):
            errors.append('No Parameters Provided')

        for line in lines:
            name, data_type, value, minimum, maximum, c, r = line.split(',')

            if data_type.strip() not in [ 'int', 'float' ]:
                errors.append('Datatype must be int for float, for %s' % (name))

            if float(minimum) > float(maximum):
                errors.append('Max does not exceed Min, for %s' % (name))

            if not (float(minimum) <= float(value) <= float(maximum)):
                errors.append('Value must be within [Min, Max], for %s' % (name))

            if data_type.strip() == 'float' and float(c) <= 0.00:
                errors.append('C for floats must be > 0.00, for %s' % (name))

            if float(r) <= 0.00:
                errors.append('R must be > 0.00, for %s' % (name))

    except:
        traceback.print_exc()
        errors.append('Malformed SPSA Input')

def verify_spsa_reporting_type(errors, request, field, field_name):
    candidates = ['BULK', 'BATCHED']
    try: assert request.POST[field] in candidates
    except: errors.append('%s must be in %s' % (field_name, ', '.join(candidates)))

def verify_spsa_distribution_type(errors, request, field, field_name):
    candidates = ['SINGLE', 'MULTIPLE']
    try: assert request.POST[field] in candidates
    except: errors.append('%s must be in %s' % (field_name, ', '.join(candidates)))

def verify_upload_pgns(errors, request, field, field_name):
    try: request.POST[field] in ['FALSE', 'COMPACT', 'VERBOSE']
    except: errors.append('"%s" must be FALSE, COMPACT, or VERBOSE' % (field_name))

def verify_datagen_games(errors, request, field):
    try: assert int(request.POST[field]) > 0
    except: errors.append('Data Generation must last for at least one game')

def verify_datagen_genfens(errors, request, field):
    try: assert '"' not in request.POST[field]
    except: errors.append('Quotes are not allowed in genfens args')

def verify_datagen_reverse(errors, request, field):
    try: assert request.POST[field] in ['YES', 'NO']
    except: errors.append('Play Reverses must either be YES or NO')

def verify_datagen_book(errors, request, field, field_name, parent):
    try:
        valid = ['NONE'] + list(OpenBench.config.OPENBENCH_CONFIG[parent].keys())
        assert request.POST[field] in valid
    except: errors.append('{0} was neither NONE nor found in the configuration'.format(field_name))


def collect_github_info(errors, request, field):

    # Get branch name / commit sha / tag, and the API path for it
    branch = request.POST['{0}_branch'.format(field)]
    bysha  = bool(re.search('^[0-9a-fA-F]{40}$', branch))

    # All API requests will share this common path. Some engines are private.
    base    = request.POST['%s_repo' % (field)].replace('github.com', 'api.github.com/repos')
    engine  = request.POST['%s_engine' % (field)]
    private = OpenBench.config.OPENBENCH_CONFIG['engines'][engine]['private']
    headers = {}

    ## Step 1: Verify the target of the API requests
    ## [A] We will not attempt to reach any site other than api.github.com
    ## [B] Private engines may only use their main repo for sources of tests
    ## [C] Determine which, if any, credentials we want to pass along

    # Private engines must have a token stored in credentials.enginename
    if private and not (headers := OpenBench.utils.read_git_credentials(engine)):
        errors.append('Server does not have access tokens for this engine')
        return (None, None)

    # Do not allow private engines to use forked repos ( We don't have a token! )
    if requests_illegal_fork(request, field):
        errors.append('Forked Repositories are not allowed for Private engines')
        return (None, None)

    # Avoid leaking our credentials to other websites
    if not base.startswith('https://api.github.com/'):
        errors.append('OpenBench may only reach Github\'s API')
        return (None, None)

    ## Step 2: Connect to the Github API for the given Branch or Commit SHA.
    ## [A] We will attempt to parse the most recent commit message for a
    ##     bench, unless one was supplied.
    ## [B] We will translate any branch name into a commit SHA for later use,
    ##     so we may compare branches and generate diff URLs
    ## [C] If the engine is public, we will construct the URL to download the
    ##     source code from Github into a .zip file.
    ## [D] If the engine is private, we will carry onto Step 3.

    try: # Fetch data from the Github API

        # Lookup branch or commit sha, but will fail for tags
        url  = OpenBench.utils.path_join(base, 'commits' if bysha else 'branches', branch)
        data = requests.get(url, headers=headers).json()

        # Check to see if the branch name was actually a tag name
        if not bysha and 'commit' not in data:
            url  = OpenBench.utils.path_join(base, 'commits', branch)
            data = requests.get(url, headers=headers).json()

        # Actual branches have to go one layer deeper
        elif not bysha: data = data['commit']

        # Check that all the data we need going forward is present
        assert 'message' in data['commit'] and 'sha' in data
        assert private or 'sha' in data['commit']['tree']

    except: # Unable to find for whatever reason
        traceback.print_exc()
        errors.append('%s could not be found' % (branch or 'Branch'))
        return (None, None)

    # Extract the bench from the web form, or from the commit message
    if not (bench := determine_bench(request, field, data['commit']['message'])):
        errors.append('Unable to parse a Bench for %s' % (branch))
        return (None, None)

    # Public Engines: Construct the .zip download and return everything
    if not private:
        treeurl = data['commit']['tree']['sha'] + '.zip'
        source  = OpenBench.utils.path_join(request.POST['%s_repo' % (field)], 'archive', treeurl)
        return (source, branch, data['sha'], bench), True

    ## Step 3: Construct the URL for the API request to list all Artifacts
    ## [A] OpenBench artifacts are always run via a file named openbench.yml
    ## [B] These should contain combinations for windows/linux, avx2/avx512, popcnt/pext
    ## [C] If those artifacts are not found, we flag the test as awaiting, and try later.

    url, has_all = fetch_artifact_url(base, engine, headers, data['sha'])
    return (url, branch, data['sha'], bench), has_all

def requests_illegal_fork(request, field):

    # Strip trailing '/'s for sanity
    engine  = OpenBench.config.OPENBENCH_CONFIG['engines'][request.POST['%s_engine' % (field)]]
    eng_src = engine['source'].rstrip('/')
    tar_src = request.POST['%s_repo' % (field)].rstrip('/')

    # Illegal if sources do not match for Private engines
    return engine['private'] and eng_src != tar_src

def determine_bench(request, field, message):

    # Use the provided bench if possible
    try: return int(request.POST['{0}_bench'.format(field)])
    except: pass

    # Fallback to try to parse the Bench from the commit
    try:
        benches = re.findall('(?:BENCH|NODES)[ :=]+([0-9,]+)', message, re.IGNORECASE)
        return int(benches[-1].replace(',', ''))
    except: return None

def fetch_artifact_url(base, engine, headers, sha):

    try:
        # Fetch the run id for the openbench workflow for this comment
        url    = OpenBench.utils.path_join(base, 'actions', 'workflows', 'openbench.yml', 'runs')
        url   += '?head_sha=%s' % (sha)
        run_id = requests.get(url=url, headers=headers).json()['workflow_runs'][0]['id']

        # Fetch information about individual job results
        url  = OpenBench.utils.path_join(base, 'actions', 'runs', str(run_id), 'jobs')
        jobs = requests.get(url=url, headers=headers).json()['jobs']

        # Fetch information about individual artifact
        url       = OpenBench.utils.path_join(base, 'actions', 'runs', str(run_id), 'artifacts')
        artifacts = requests.get(url=url, headers=headers).json()['artifacts']

        # All jobs finished, with at least one non-expired Artifact
        assert not any(job['conclusion'] != 'success' for job in jobs)
        assert not any(artifact['expired'] for artifact in artifacts)
        assert len(artifacts) >= len(jobs)

        # Only set the url if we have everything we need
        return (url, True)

    except Exception as error:
        # If anything goes wrong, retry later with the same base URL
        return (base, False)