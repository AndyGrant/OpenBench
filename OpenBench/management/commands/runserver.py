import django.apps
import requests, sys, threading, time
import OpenBench.utils

from django.core.management.commands.runserver import Command as BaseRunserverCommand

class ArtifactWatcher(threading.Thread):

    def check_for_artifacts(self, data):

        # Success, if we had all artifacts. Otherwise consider re-running the Workflow
        retval, has_all = OpenBench.utils.fetch_artifact_url(*data, return_data=True)
        if has_all: return retval, True

        # Otherwise, we may have returned the Jobs + Artifacts
        jobs, artifacts = retval

        # Catch expired artifacts, or a Github API bug and run the Workflow
        if all(job['conclusion'] == 'success' for job in jobs):
            run_id = jobs[0]['run_id']
            url    = OpenBench.utils.path_join(data[0], 'actions', 'runs', str(run_id), 'rerun')
            requests.post(url=url, headers=data[2]).json()

        # We did not have all artifacts needed, return the original source
        return data[0], False

    def update_test(self, test):

        # Check for Artifacts for Dev, and re-run if needed
        if not (dev_has_all := test.dev.source.endswith('artifacts')):
            dev_headers = OpenBench.utils.read_git_credentials(test.dev_engine)
            data = [test.dev.source, test.dev_engine, dev_headers, test.dev.sha]
            test.dev.source, dev_has_all = self.check_for_artifacts(data)
            test.dev.save()

        # Check for Artifacts for Base, and re-run if needed
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
