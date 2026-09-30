"""Keeping hold of a login across the moments Home Assistant cannot be reached."""

import io
import json
import threading
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


class TwoAskers(unittest.TestCase):
    """The session and the camera stills may both find the token expiring."""

    def test_only_one_of_them_renews_it(self):
        auth = ha_auth.Authenticator("http://ha.invalid", username="kodi",
                                     password="secret")
        auth._refresh_token = "refresh"
        renewing, release, renewals = threading.Event(), threading.Event(), []

        def refresh():
            renewals.append(1)
            renewing.set()
            release.wait(5)
            return auth._store({"access_token": "fresh", "expires_in": 1800})

        auth._refresh = refresh
        first = threading.Thread(target=auth.access_token)
        first.start()
        renewing.wait(5)
        second = threading.Thread(target=auth.access_token)
        second.start()
        second.join(0.2)  # long enough to reach the refresh, were it free
        release.set()
        first.join(5)
        second.join(5)
        self.assertEqual(len(renewals), 1)


if __name__ == "__main__":
    unittest.main()
