"""The dashboard window, as far as it can be driven without Kodi."""

import unittest
from unittest import mock

from . import fakekodi  # noqa: F401  (stands in for Kodi's modules)
from . import support
from resources.lib import actions, model, window


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


class EnteringNumbers(unittest.TestCase):
    """What a number dialog is opened with, and what comes back of it."""

    def ask(self, action, answers, **attributes):
        board = dashboard()
        board._store.states = {"x.y": model.State(support.state("x.y", "5", **attributes))}
        with mock.patch.object(window.xbmcgui, "Dialog") as dialog:
            dialog.return_value.input.side_effect = answers
            dialog.return_value.numeric.side_effect = answers
            data = board._collect_input("x.y", action)
        self.asked = [call.args[1] for call in dialog.return_value.input.call_args_list]
        self.padded = [call.args[2] for call in dialog.return_value.numeric.call_args_list]
        return data

    def temperature(self, answers, **attributes):
        return self.ask(actions.Action("action_set_temperature", actions.TEMPERATURE,
                                       "climate", "set_temperature"), answers, **attributes)

    def test_a_thermostat_takes_half_degrees(self):
        self.assertEqual(self.temperature(["22.5"], temperature=21.5), {"temperature": 22.5})
        self.assertEqual(self.asked, ["21.5"])

    def test_its_own_step_wins(self):
        self.assertEqual(self.temperature(["22"], temperature=21, target_temp_step=1),
                         {"temperature": 22.0})
        self.assertEqual(self.padded, ["21"])

    def test_a_range_is_asked_for_end_by_end(self):
        data = self.temperature(["19.5", "23,5"], hvac_mode="heat_cool", temperature=None,
                                target_temp_low=19, target_temp_high=24)
        self.assertEqual(data, {"target_temp_low": 19.5, "target_temp_high": 23.5})
        self.assertEqual(self.asked, ["19.0", "24.0"])

    def test_nothing_known_is_not_offered_as_zero(self):
        self.temperature([""], temperature=None)
        self.assertEqual(self.asked + self.padded, [""])

    def test_a_number_keeps_the_places_of_its_step(self):
        action = actions.Action("action_set_value", actions.NUMBER, "number", "set_value")
        self.assertEqual(self.ask(action, ["0.75"], step=0.25), {"value": 0.75})
        self.assertEqual(self.asked, ["5.00"])

    def test_a_position_stays_on_the_number_pad(self):
        action = actions.Action("action_position", actions.NUMBER, "cover",
                                "set_cover_position")
        self.assertEqual(self.ask(action, ["55"], current_position=40), {"position": 55.0})
        self.assertEqual(self.padded, ["40"])


if __name__ == "__main__":
    unittest.main()
