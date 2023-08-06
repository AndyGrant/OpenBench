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

import requests
import sys
import threading
import time
import traceback

import OpenBench.utils

class ArtifactWatcher(threading.Thread):

    def update_test(self, test):

        # Public engines end their source with .zip. Private engines end
        # their source with /artifacts, iff the artifacts have been found

        dev_has = test.dev.source.endswith('artifacts')
        dev_has = test.dev.source.endswith('.zip') or dev_has

        base_has = test.base.source.endswith('artifacts')
        base_has = test.base.source.endswith('.zip') or base_has

        if not dev_has: # Check for new Artifacts for Dev
            dev_headers = OpenBench.utils.read_git_credentials(test.dev_engine)
            data = [test.dev.source, test.dev_engine, dev_headers, test.dev.sha]
            test.dev.source, dev_has = OpenBench.utils.fetch_artifact_url(*data)
            test.dev.save()

        if not base_has: # Check for new Artifacts for Base
            base_headers = OpenBench.utils.read_git_credentials(test.base_engine)
            data = [test.base.source, test.base_engine, base_headers, test.base.sha]
            test.base.source, base_has = OpenBench.utils.fetch_artifact_url(*data)
            test.base.save()

        # If both finished, flag the test as no longer awaiting
        if dev_has and base_has:
            test.awaiting = False
            test.save()

    def run(self):
        while True:
            for test in OpenBench.utils.get_awaiting_tests():
                try: self.update_test(test)
                except:
                    traceback.print_exc()
                    sys.stdout.flush()
            time.sleep(15)
