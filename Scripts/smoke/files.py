# The engine source and the opening book, served the way the worker fetches them:
# a plain GET of a zip, shaped like GitHub's archive/<sha>.zip (one root entry).

import hashlib
import io
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SMOKE_DIR  = Path(__file__).resolve().parent
ENGINE_DIR = SMOKE_DIR / 'engine'
BOOK_FILE  = SMOKE_DIR / 'book.epd'
BOOK_NAME  = 'smoke.epd'


# A makefile whose compiler fails the way g++ does: the file and line, then the error
BROKEN_MAKEFILE = (
    'all:\n'
    '\t@echo "src/eval/mobility.cpp:212:9: error: mobility was not declared in this scope" >&2\n'
    '\t@exit 2\n')


def engine_zip(root_name, broken=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.write(ENGINE_DIR / 'engine.py', '%s/engine.py' % (root_name))
        if broken:
            archive.writestr('%s/makefile' % (root_name), BROKEN_MAKEFILE)
        else:
            archive.write(ENGINE_DIR / 'makefile', '%s/makefile' % (root_name))
    return buffer.getvalue()


def book_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(BOOK_NAME, BOOK_FILE.read_bytes())
    return buffer.getvalue()


def book_sha():
    # The worker hashes the extracted book as text, which is the bytes on Linux
    return hashlib.sha256(BOOK_FILE.read_bytes()).hexdigest()


class FileServer:

    def __init__(self):
        self.files    = {}
        self.requests = []

        server = self

        class Handler(BaseHTTPRequestHandler):

            def do_GET(self):
                server.requests.append(self.path)
                body = server.files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/zip')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd  = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url    = 'http://127.0.0.1:%d' % (self.httpd.server_address[1])
        self.thread = threading.Thread(target=self.httpd.serve_forever, name='smoke-files', daemon=True)

    def add(self, path, body):
        self.files[path] = body
        return self.url + path

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
