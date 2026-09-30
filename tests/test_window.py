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


class Home:
    """Stands in for Home Assistant: a light that is switched on mid-load.

    The change is told to whoever has subscribed by then, as Home Assistant
    tells it, and to nobody else.
    """

    version = "2026.9.0"

    def __init__(self):
        self.listeners = []

    def subscribe(self, callback, type_="subscribe_events", **payload):
        if payload.get("event_type") == "state_changed":
            self.listeners.append(callback)
        return len(self.listeners)

    def command(self, type_, **payload):
        if type_ == "get_states":
            for listener in self.listeners:
                listener({"data": {"entity_id": "light.a", "new_state": {
                    "entity_id": "light.a", "state": "on", "attributes": {}}}})
            return [{"entity_id": "light.a", "state": "off", "attributes": {}}]
        if type_.endswith("_registry/list"):
            return []
        return {}


class Connecting(unittest.TestCase):
    def test_a_change_during_the_first_load_is_kept(self):
        board = dashboard()
        board._on_ready(Home())
        self.assertEqual(board._store.states["light.a"].state, "on")


class Tokens:
    """Stands in for the authenticator: a new token every time it is asked."""

    def __init__(self):
        self.handed_out = 0

    def access_token(self):
        self.handed_out += 1
        return "token-%d" % self.handed_out


class Recorder:
    """Stands in for the snapshots: remembers the token each still went with."""

    def __init__(self):
        self.tokens = []

    def fetch(self, entity_id, token):
        self.tokens.append(token)
        return ""


class CameraStills(unittest.TestCase):
    def test_every_round_asks_for_the_token_as_it_is_now(self):
        board = dashboard()
        board._auth = Tokens()
        board._image_token = board._auth.access_token()  # as at connect
        board._snapshots = Recorder()
        board._row_positions = {"camera.tuer": 0}
        for _ in range(2):
            board._camera_due = 0.0
            board._take_camera_stills()
            board._camera_worker.join(5)
        self.assertEqual(board._snapshots.tokens, ["token-2", "token-3"])


if __name__ == "__main__":
    unittest.main()
