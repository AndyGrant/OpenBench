#!/usr/bin/env python
import os
import signal
import sys

# OpenBench.apps registers an atexit shutdown() that gracefully stops the PGN
# and Artifact watcher threads -- joining them so any in-flight tar write is
# allowed to finish. atexit only runs on a clean interpreter exit, not on a
# bare SIGTERM, so we install a SIGTERM handler that turns the kill signal into
# a clean sys.exit() and thereby triggers that atexit shutdown().
#
# signal.signal() may only be called from the main thread, and ready() (where
# the watchers are spawned) is not guaranteed to run there. So the handler is
# installed at the two process entry points instead, each of which IS the main
# thread of its own process:
#
#     manage.py        -> the entry point for `runserver`        (here)
#     OpenSite/wsgi.py -> the module gunicorn imports per worker (the gunicorn case)
#
# Whichever entry point starts the process installs the handler; the other
# no-ops for that run (under runserver, wsgi.py is imported off the main thread
# and skips itself). Keep this block and the handler in sync across both files.
#
# Ignore any further SIGTERMs so the atexit shutdown runs to completion. A
# `pkill -TERM gunicorn` hits each worker directly AND the arbiter, which
# then broadcasts a second SIGTERM to every worker; without this the second
# signal would re-enter here and abort the shutdown partway through.

def graceful_exit_on_sigterm(*args):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    sys.exit(0)

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "OpenSite.settings")

    signal.signal(signal.SIGTERM, graceful_exit_on_sigterm)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)
