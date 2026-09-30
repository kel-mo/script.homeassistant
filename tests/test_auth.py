"""Keeping hold of a login across the moments Home Assistant cannot be reached."""

import io
import json
import unittest
import urllib.error
from unittest import mock

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib.ha import auth as ha_auth


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def refusing(code, body):
    return urllib.error.HTTPError("http://ha.invalid/auth/token", code, "refused",
                                  {}, io.BytesIO(json.dumps(body).encode("utf-8")))


class Refreshing(unittest.TestCase):
    def setUp(self):
        self.auth = ha_auth.Authenticator("http://ha.invalid", username="kodi",
                                          password="secret")
        self.auth._refresh_token = "refresh"
        self.asked = []

    def answer(self, *outcomes):
        """urlopen, answering each request with the next outcome in turn."""
        outcomes = list(outcomes)

        def urlopen(request, **kwargs):
            self.asked.append(request.full_url)
            if not outcomes:
                raise AssertionError("not expected: %s" % request.full_url)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return Response(json.dumps(outcome).encode("utf-8"))
        return mock.patch("urllib.request.urlopen", urlopen)

    def test_an_unreachable_server_leaves_the_refresh_token_alone(self):
        with self.answer(urllib.error.URLError("Connection refused")):
            self.assertRaises(ha_auth.AuthError, self.auth.access_token)
        self.assertEqual(self.auth._refresh_token, "refresh")
        # And no login is started behind the user's back.
        self.assertEqual(self.asked, ["http://ha.invalid/auth/token"])

    def test_so_does_a_proxy_standing_in_for_a_restarting_one(self):
        with self.answer(refusing(502, {"message": "Bad Gateway"})):
            self.assertRaises(ha_auth.AuthError, self.auth.access_token)
        self.assertEqual(self.auth._refresh_token, "refresh")

    def test_a_refused_refresh_token_is_dropped_for_a_new_login(self):
        with self.answer(refusing(400, {"error": "invalid_grant"}),
                         urllib.error.URLError("Connection refused")):
            self.assertRaises(ha_auth.AuthError, self.auth.access_token)
        self.assertEqual(self.auth._refresh_token, "")
        self.assertEqual(self.asked, ["http://ha.invalid/auth/token",
                                      "http://ha.invalid/auth/login_flow"])

    def test_the_next_refresh_carries_on_once_it_is_back(self):
        with self.answer(urllib.error.URLError("Connection refused"),
                         {"access_token": "fresh", "expires_in": 1800}):
            self.assertRaises(ha_auth.AuthError, self.auth.access_token)
            self.assertEqual(self.auth.access_token(), "fresh")


if __name__ == "__main__":
    unittest.main()
