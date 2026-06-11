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

import os
import sys
import tarfile
import threading
import traceback

from OpenBench.models import PGN

from django.core.files.storage import FileSystemStorage

# Max PGN rows handled per pass. Drains a backlog in chunks, and bounds how long
# a graceful shutdown's join() can block (one batch, never the whole backlog).
PGN_BATCH_SIZE = 128

class PGNWatcher(threading.Thread):

    def __init__(self, stop_event, *args, **kwargs):
        self.stop_event = stop_event
        super().__init__(*args, **kwargs)

    def process_test(self, storage, test_id, pgns):

        # Bulk add individual .bz2 PGNs to the archive. We bulk add in order to avoid
        # scanning the entire archive on every individual write, which is very slow.

        tar_path = storage.path('PGNs/%d.pgn.tar' % (test_id))
        os.makedirs(os.path.dirname(tar_path), exist_ok=True)

        mode = 'a' if os.path.exists(tar_path) else 'w'
        with tarfile.open(tar_path, mode) as tar:
            for pgn in pgns:
                tar.add(storage.path(pgn.filename()), arcname=pgn.filename())

        # Flag each of the PGNs as having been processed into the archive
        PGN.objects.filter(pk__in=[pgn.pk for pgn in pgns]).update(processed=True)

        # Only delete the files after flagging; in case something goes wrong
        for pgn in pgns:
            storage.delete(pgn.filename())

    def process_pending(self):

        # Bounded slice, ordered by test so a test's PGNs share one tar open.
        pgns = list(PGN.objects.filter(processed=False).order_by('test_id')[:PGN_BATCH_SIZE])

        # Group by test_id, then process each test's PGNs as one batch
        groups = {}
        for pgn in pgns:
            groups.setdefault(pgn.test_id, []).append(pgn)

        for test_id, group in groups.items():
            self.process_test(FileSystemStorage(), test_id, group)

        return len(pgns)

    def run(self):
      
        # Loop until we are shutdown by the atexit.register()
        while not self.stop_event.is_set():

            # Never exit on errors, to keep the watcher alive
            try:
                handled = self.process_pending()

            # We expect -some- "database is locked" errors
            except Exception as error:
                handled = 0
                if 'database is locked' not in str(error).lower():
                    traceback.print_exc()
                    sys.stdout.flush()

            # If we only processed a partial patch, we can go into our sleep
            # Otherwise loop again immediately, which will check the stop_event
            if handled < PGN_BATCH_SIZE:
                self.stop_event.wait(timeout=15)
