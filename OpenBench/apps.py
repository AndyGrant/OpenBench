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

import django.apps
import threading, time

class ArtifactWatcher(threading.Thread):

    def run(self):

        # Delay imports due to the app not having been loaded yet
        import OpenBench.utils

        while True:

            time.sleep(30)

            for test in OpenBench.utils.get_awaiting_tests():

                dev_has_all  = test.dev.source.endswith('artifacts')
                base_has_all = test.base.source.endswith('artifacts')
                headers      = OpenBench.utils.read_git_credentials(test.engine)

                if headers and not dev_has_all:
                    test.dev.source, dev_has_all = OpenBench.utils.fetch_artifact_url(
                        test.dev.source, test.engine, headers, test.dev.sha)
                    test.dev.save()

                if headers and not base_has_all:
                    test.base.source, base_has_all = OpenBench.utils.fetch_artifact_url(
                        test.base.source, test.engine, headers, test.base.sha)
                    test.base.save()

                if dev_has_all and base_has_all:
                    test.awaiting = False
                    test.save()

class OpenbenchConfig(django.apps.AppConfig):

    name = 'OpenBench'

    def ready(self):
        self.watcher = ArtifactWatcher().start()
