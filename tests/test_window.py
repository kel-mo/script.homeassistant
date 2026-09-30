"""The dashboard window, as far as it can be driven without Kodi."""

import unittest

from . import fakekodi  # noqa: F401  (stands in for Kodi's modules)
from resources.lib import window


class Settings:
    url = "http://ha.invalid:8123"
    token = "long-lived"
    username = password = ""
    verify_ssl = True
    favourites = summaries = areas = hide_empty_areas = True
    camera_refresh = 10


def dashboard():
    return window.Dashboard("dashboard.xml", "", "Default", "1080i",
                            settings=Settings())


class LosingTheConnection(unittest.TestCase):
    def test_a_drop_promises_a_reconnect(self):
        board = dashboard()
        board._on_lost("connection reset")
        self.assertEqual(board._status_text, "Reconnecting ...")
        self.assertIsNone(board._message_text)

    def test_a_refusal_says_why_and_promises_nothing(self):
        board = dashboard()
        board._on_lost("token rejected", True)
        self.assertEqual(board._status_text, "Not connected")
        self.assertEqual(board._message_text, "Authentication failed: token rejected")


if __name__ == "__main__":
    unittest.main()
