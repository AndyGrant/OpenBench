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

import atexit
import pathlib
import platform
import threading

import django.apps

# No imports of OpenBench.* are allowed here

LOCKFILE_PATH = 'openbench_watchers.lock'
CONFIG_LOCK   = threading.Lock()
IS_WINDOWS    = platform.system() == 'Windows'

def acquire_watcher_lockfile():

    lockfile = None

    try: # Failed to open the file entirely
        lockfile = open(LOCKFILE_PATH, 'w')
    except: return None

    try:

        if IS_WINDOWS:
            import msvcrt
            msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)

        else:
            import fcntl
            fcntl.lockf(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)

    except: # Failed to acquire the lock, but must still close the file
        lockfile.close()
        return None

    return lockfile

class OpenBenchConfig(django.apps.AppConfig):

    name = 'OpenBench'

    def ready(self):

        # Load all of the .json config files, only once per PROCESS.
        # This must be done before ANY other OpenBench includes are used.

        from OpenBench import config

        with CONFIG_LOCK:
            if config.OPENBENCH_CONFIG is None:
                config.OPENBENCH_CONFIG, config.OPENBENCH_CONFIG_CHECKSUM = config.create_openbench_config()

        # Attempt to spawn the PGN Watcher, globally once

        from OpenBench.pgn_watcher import PGNWatcher

        # Result of fopen(LOCKFILE_PATH) after obtaining the lock, otherwise None
        self.lockfile = acquire_watcher_lockfile()

        if self.lockfile:

            # Start a PGN Watcher
            self.stop_pgn_watcher = threading.Event()
            self.pgn_watcher = PGNWatcher(self.stop_pgn_watcher, daemon=True)
            self.pgn_watcher.start()

            # We expect a nice sys.exit(0) to allow our atexit to execute
            atexit.register(self.shutdown)

    def shutdown(self):

        # Signal the PGN Watcher to shutdown
        if hasattr(self, 'pgn_watcher') and self.pgn_watcher.is_alive():
            self.stop_pgn_watcher.set()
            self.pgn_watcher.join()

        # Cleanup Lockfile if we hold it
        if self.lockfile:
            self.lockfile.close()
            pathlib.Path(LOCKFILE_PATH).unlink(missing_ok=True)
