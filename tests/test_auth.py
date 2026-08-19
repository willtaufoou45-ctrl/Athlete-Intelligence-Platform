import unittest
import io
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from aip.auth import csrf_valid, issue_session, password_hash, read_session, verify_password
from aip.config import Config
from aip.web import create_app


class AuthenticationTests(unittest.TestCase):
    def test_scrypt_password_hash_verifies_without_storing_plaintext(self):
        encoded = password_hash("a long field password", salt=b"0123456789abcdef")
        self.assertTrue(verify_password("a long field password", encoded))
        self.assertFalse(verify_password("incorrect password", encoded))
        self.assertNotIn("long field password", encoded)

    def test_signed_session_rejects_tampering_and_expiry(self):
        token, csrf = issue_session("coach", "s" * 32, now=100)
        environ = {"HTTP_COOKIE": f"aip_session={token}"}
        session = read_session(environ, "s" * 32, now=101)
        self.assertEqual(session["sub"], "coach")
        self.assertTrue(csrf_valid({}, session, csrf))
        self.assertIsNone(read_session(environ, "x" * 32, now=101))
        self.assertIsNone(read_session(environ, "s" * 32, now=100 + 12 * 60 * 60 + 1))

    def test_hosted_app_requires_login_and_csrf_for_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(
                database_url=str(Path(directory) / "auth.sqlite3"), hosted=True,
                auth_enabled=True, coach_username="coach",
                coach_password_hash=password_hash("a long field password"),
                session_secret="s" * 32, trusted_proxy=True,
            )
            app = create_app(config=config)
            denied = call(app, "GET", "/")
            self.assertEqual(denied["status"], "303 See Other")
            self.assertEqual(denied["headers"]["Location"], "/login")

            login = call(app, "POST", "/login", {
                "username": "coach", "password": "a long field password",
            }, form=True, forwarded_proto="https")
            cookie = login["headers"]["Set-Cookie"].split(";", 1)[0]
            self.assertIn("Secure", login["headers"]["Set-Cookie"])
            home = call(app, "GET", "/", cookie=cookie, forwarded_proto="https")
            csrf = re.search(rb"name='csrf-token' content='([^']+)'", home["body"]).group(1).decode()
            rejected = call(app, "POST", "/athletes", {"name": "Runner"}, form=True, cookie=cookie)
            accepted = call(app, "POST", "/athletes", {
                "name": "Runner", "csrf_token": csrf,
            }, form=True, cookie=cookie)
            self.assertEqual(rejected["status"], "403 Forbidden")
            self.assertEqual(accepted["status"], "303 See Other")
            self.assertIn("Strict-Transport-Security", home["headers"])


def call(app, method, path, data=None, *, form=False, cookie="", forwarded_proto=""):
    payload = (urlencode(data or {}) if form else json.dumps(data or {})).encode()
    environ = {
        "REQUEST_METHOD": method, "PATH_INFO": path, "CONTENT_LENGTH": str(len(payload)),
        "CONTENT_TYPE": "application/x-www-form-urlencoded" if form else "application/json",
        "REMOTE_ADDR": "127.0.0.1", "wsgi.input": io.BytesIO(payload),
        "HTTP_COOKIE": cookie, "HTTP_X_FORWARDED_PROTO": forwarded_proto,
    }
    response = {}
    def start(status, headers):
        response["status"], response["headers"] = status, dict(headers)
    response["body"] = b"".join(app(environ, start))
    return response


if __name__ == "__main__":
    unittest.main()
