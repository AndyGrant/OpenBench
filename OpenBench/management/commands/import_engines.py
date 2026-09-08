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

# Create or update EngineConfigs from the legacy Engines/<name>.json format:
#
# >>> python3 manage.py import_engines Engines/
# >>> python3 manage.py import_engines Engines/Ethereal.json
#
# The EngineConfig takes its name from the file name, sans the .json suffix.
# Existing Engines are updated in place, leaving their enabled flag alone.

import json
import os

from django.core.management.base import BaseCommand, CommandError

from OpenBench.config import PRESET_TYPES, verify_engine_presets
from OpenBench.models import EngineConfig

class Command(BaseCommand):

    help = 'Create or update Engines from .json files, or directories of them'

    def add_arguments(self, parser):
        parser.add_argument('paths', nargs='+', help='.json files, or directories containing them')

    def handle(self, *args, **options):

        for path in options['paths']:
            for fname in expand_path(path):

                with open(fname) as fin:
                    conf = json.load(fin)

                name   = os.path.basename(fname).removesuffix('.json')
                fields = engine_fields(fname, name, conf)

                engine, created = EngineConfig.objects.update_or_create(name=name, defaults=fields)
                self.stdout.write('%s %s' % ('Created' if created else 'Updated', engine.name))

def engine_fields(fname, name, conf):

    if type(conf.get('build')) != dict:
        raise CommandError('%s is missing a "build" object' % (fname))

    if type(conf.get('nps')) != int or conf['nps'] <= 0:
        raise CommandError('%s must contain a positive integer "nps"' % (fname))

    if type(conf.get('source')) != str:
        raise CommandError('%s must contain a string "source"' % (fname))

    if type(conf.get('private')) != bool:
        raise CommandError('%s must contain a boolean "private"' % (fname))

    # Missing preset types were previously filled in when the file was loaded
    presets = { x : conf.get(x) or { 'default' : {} } for x in PRESET_TYPES }
    for group in presets.values():
        group.setdefault('default', {})

    if (error := verify_engine_presets(presets)):
        raise CommandError('%s %s' % (fname, error))

    build = conf['build']

    return {
        'private'         : conf['private'],
        'nps'             : conf['nps'],
        'source'          : conf['source'],
        'build_path'      : build.get('path', ''),
        'build_compilers' : ' '.join(build.get('compilers', [])),
        'build_cpuflags'  : ' '.join(build.get('cpuflags', [])),
        'build_systems'   : ' '.join(build.get('systems', [])),
        'presets'         : presets,
    }

def expand_path(path):

    if os.path.isfile(path):
        return [path]

    if os.path.isdir(path):
        return [os.path.join(path, x) for x in sorted(os.listdir(path)) if x.endswith('.json')]

    raise CommandError('No such file or directory: %s' % (path))
