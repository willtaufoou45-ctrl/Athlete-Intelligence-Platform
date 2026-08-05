import unittest
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer

from main import ThreadedWSGIServer


class LauncherTests(unittest.TestCase):
    def test_local_server_handles_browser_connections_concurrently(self):
        self.assertTrue(issubclass(ThreadedWSGIServer, ThreadingMixIn))
        self.assertTrue(issubclass(ThreadedWSGIServer, WSGIServer))
        self.assertTrue(ThreadedWSGIServer.daemon_threads)


if __name__ == "__main__":
    unittest.main()
