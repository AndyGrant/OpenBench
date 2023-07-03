import django.apps
import requests, sys, threading, time
import OpenBench.utils

from django.core.management.commands.runserver import Command as BaseRunserverCommand

class ArtifactWatcher(threading.Thread):

    def check_for_artifacts(self, data):
        return OpenBench.utils.fetch_artifact_url(*data)

    def update_test(self, test):

        # Check for Artifacts for Dev
        if not (dev_has_all := test.dev.source.endswith('artifacts')):
            dev_headers = OpenBench.utils.read_git_credentials(test.dev_engine)
            data = [test.dev.source, test.dev_engine, dev_headers, test.dev.sha]
            test.dev.source, dev_has_all = self.check_for_artifacts(data)
            test.dev.save()

        # Check for Artifacts for Base
        if not (base_has_all := test.base.source.endswith('artifacts')):
            base_headers = OpenBench.utils.read_git_credentials(test.base_engine)
            data = [test.base.source, test.base_engine, base_headers, test.base.sha]
            test.base.source, base_has_all = self.check_for_artifacts(data)
            test.base.save()

        # If both finished, flag the test as no longer awaiting
        if dev_has_all and base_has_all:
            test.awaiting = False
            test.save()

    def run(self):
        while True:
            for test in OpenBench.utils.get_awaiting_tests():
                try: self.update_test(test)
                except:
                    import traceback, sys
                    traceback.print_exc()
                    sys.stdout.flush()
            time.sleep(15)

class Command(BaseRunserverCommand):

    def inner_run(self, *args, **options):
        self.pre_start()
        super().inner_run(*args, **options)
        self.pre_quit()

    def pre_start(self):
        self.watcher = ArtifactWatcher().start()

    def pre_quit(self):
        self.watcher.kill()
