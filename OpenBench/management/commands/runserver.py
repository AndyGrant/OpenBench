import django.apps
import threading, time
import OpenBench.utils

from django.core.management.commands.runserver import Command as BaseRunserverCommand

class ArtifactWatcher(threading.Thread):

    def update_test(self, test):

        dev_has_all  = test.dev.source.endswith('artifacts')
        base_has_all = test.base.source.endswith('artifacts')

        dev_headers  = OpenBench.utils.read_git_credentials(test.dev_engine)
        base_headers = OpenBench.utils.read_git_credentials(test.base_engine)

        if dev_headers and not dev_has_all:
            test.dev.source, dev_has_all = OpenBench.utils.fetch_artifact_url(
                test.dev.source, test.dev_engine, dev_headers, test.dev.sha)
            test.dev.save()

        if base_headers and not base_has_all:
            test.base.source, base_has_all = OpenBench.utils.fetch_artifact_url(
                test.base.source, test.base_engine, base_headers, test.base.sha)
            test.base.save()

        if dev_has_all and base_has_all:
            test.awaiting = False
            test.save()

    def run(self):
        while True:
            for test in OpenBench.utils.get_awaiting_tests():
                self.update_test(test)
            time.sleep(10)

class Command(BaseRunserverCommand):

    def inner_run(self, *args, **options):
        self.pre_start()
        super().inner_run(*args, **options)
        self.pre_quit()

    def pre_start(self):
        self.watcher = ArtifactWatcher().start()

    def pre_quit(self):
        self.watcher.kill()
