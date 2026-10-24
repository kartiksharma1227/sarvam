"""Serve the media folder over HTTP for CLI runs, so the renderer can fetch narration audio and icons."""

import functools
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _QuietHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # The renderer page (another localhost port) fetch()es icon SVGs, which needs CORS.
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, *args) -> None:
        pass


@contextmanager
def serve_media(directory: Path) -> Iterator[str]:
    """Yield a base URL (e.g. http://127.0.0.1:53712) that serves `directory` until the block exits."""
    handler = functools.partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
