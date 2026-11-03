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

# Create or update Book models from the legacy Books/<name>.json format:
#
# >>> python3 manage.py import_books Books/
# >>> python3 manage.py import_books Books/UHO_4060_v2.epd.json
#
# The Book takes its name from the file name, sans the .json suffix. Existing
# Books are updated in place, leaving both their name and enabled flag alone.

import json
import os

from django.core.management.base import BaseCommand, CommandError

from OpenBench.models import Book

class Command(BaseCommand):

    help = 'Create or update Books from .json files, or directories of them'

    def add_arguments(self, parser):
        parser.add_argument('paths', nargs='+', help='.json files, or directories containing them')

    def handle(self, *args, **options):

        for path in options['paths']:
            for fname in expand_path(path):

                with open(fname) as fin:
                    conf = json.load(fin)

                name = os.path.basename(fname).removesuffix('.json')

                if type(conf.get('sha')) != str or type(conf.get('source')) != str:
                    raise CommandError('%s must contain string "sha" and "source" fields' % (fname))

                book, created = Book.objects.update_or_create(
                    name=name, defaults={ 'source' : conf['source'], 'sha' : conf['sha'] })

                self.stdout.write('%s %s' % ('Created' if created else 'Updated', book.name))

def expand_path(path):

    if os.path.isfile(path):
        return [path]

    if os.path.isdir(path):
        return [os.path.join(path, x) for x in sorted(os.listdir(path)) if x.endswith('.json')]

    raise CommandError('No such file or directory: %s' % (path))
