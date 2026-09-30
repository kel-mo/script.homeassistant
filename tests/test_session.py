"""Getting a connection open when the endpoint is unreliable."""

import unittest

from . import support  # noqa: F401  (puts the addon on the path)
from resources.lib.ha import auth as ha_auth
from resources.lib.ha import client as ha_client


class FakeClient:
    """Stands in for HomeAssistant: fails a set number of handshakes."""

    made = []

    def __init__(self, *args, **kwargs):
        self.closed = False
        self.on_close = None
        FakeClient.made.append(self)

    def connect(self):
        failures = FakeClient.failures
        if len(FakeClient.made) <= failures:
            raise ha_client.HomeAssistantError("TLS handshake refused")
        if FakeClient.refuse_auth:
            raise ha_client.AuthFailed("token rejected")

    def close(self):
        self.closed = True


class Connecting(unittest.TestCase):
    def setUp(self):
        FakeClient.made = []
        FakeClient.failures = 0
        FakeClient.refuse_auth = False
        self.original = ha_client.HomeAssistant
        self.pause = ha_client._CONNECT_PAUSE
        ha_client.HomeAssistant = FakeClient
        ha_client._CONNECT_PAUSE = 0  # the pause is real, and not the point here
        self.session = ha_client.Session("http://ha.invalid", authenticator=None)

    def tearDown(self):
        ha_client.HomeAssistant = self.original
        ha_client._CONNECT_PAUSE = self.pause

    def test_a_flaky_endpoint_is_reached_without_waiting_out_the_backoff(self):
        FakeClient.failures = 2
        connected = self.session._connect()
        self.assertEqual(len(FakeClient.made), 3)
        self.assertFalse(connected.closed)

    def test_the_attempts_that_failed_are_closed_again(self):
        FakeClient.failures = 2
        self.session._connect()
        self.assertEqual([c.closed for c in FakeClient.made], [True, True, False])

    def test_giving_up_reports_the_last_failure(self):
        FakeClient.failures = 99
        with self.assertRaises(ha_client.HomeAssistantError) as caught:
            self.session._connect()
        self.assertIn("handshake refused", str(caught.exception))
        self.assertEqual(len(FakeClient.made), ha_client._CONNECT_ATTEMPTS)

    def test_a_rejected_token_is_not_worth_retrying(self):
        FakeClient.refuse_auth = True
        self.assertRaises(ha_client.AuthFailed, self.session._connect)
        self.assertEqual(len(FakeClient.made), 1)


class FakeWebSocket:
    """Stands in for the WebSocket: canned replies, or a failure instead."""

    made = []

    def __init__(self, *args, **kwargs):
        self.replies = list(FakeWebSocket.replies)
        self.sent = []
        self.closed = False
        self.connected = True
        self.on_send = None
        FakeWebSocket.made.append(self)

    def connect(self):
        pass

    def recv_json(self):
        if not self.replies:
            raise ha_client.WebSocketClosed(reason="gone")
        return self.replies.pop(0)

    def send_json(self, message):
        self.sent.append(message)
        if self.on_send is not None:
            self.on_send()

    def settimeout(self, timeout):
        pass

    def close(self):
        self.closed = True
        self.connected = False


class FakeAuth:
    def access_token(self):
        return "token"

    def invalidate(self):
        pass


class Handshaking(unittest.TestCase):
    def setUp(self):
        FakeWebSocket.made = []
        self.original = ha_client.WebSocket
        ha_client.WebSocket = FakeWebSocket

    def tearDown(self):
        ha_client.WebSocket = self.original

    def connect(self, *replies):
        FakeWebSocket.replies = replies
        client = ha_client.HomeAssistant("http://ha.invalid", FakeAuth())
        client.connect()
        return client

    def test_a_connection_that_drops_before_the_greeting_is_closed(self):
        self.assertRaises(ha_client.WebSocketClosed, self.connect)
        self.assertTrue(FakeWebSocket.made[0].closed)

    def test_so_is_one_that_drops_before_the_verdict(self):
        self.assertRaises(ha_client.WebSocketClosed, self.connect,
                          {"type": "auth_required"})
        self.assertTrue(FakeWebSocket.made[0].closed)

    def test_a_rejected_token_closes_the_connection_too(self):
        self.assertRaises(ha_client.AuthFailed, self.connect,
                          {"type": "auth_required"}, {"type": "auth_invalid"})
        self.assertTrue(FakeWebSocket.made[0].closed)


class ClosingMidCommand(unittest.TestCase):
    """close() runs on another thread, and may land between send and wait."""

    def client(self):
        FakeWebSocket.replies = ()
        client = ha_client.HomeAssistant("http://ha.invalid", FakeAuth())
        client._ws = FakeWebSocket()
        client._ws.on_send = client.close
        return client

    def test_a_command_says_the_connection_is_gone(self):
        self.assertRaises(ha_client.NotConnected, self.client().command, "ping")

    def test_so_does_a_subscription(self):
        self.assertRaises(ha_client.NotConnected, self.client().subscribe,
                          lambda event: None)


class RefusingClient(FakeClient):
    """Stands in for HomeAssistant: every connect fails with the same error."""

    def connect(self):
        raise RefusingClient.error


class LongLived:
    def __init__(self, long_lived):
        self.uses_long_lived_token = long_lived


class GivingUp(unittest.TestCase):
    """A refusal that trying again would only repeat ends the session."""

    def setUp(self):
        FakeClient.made = []
        self.original = ha_client.HomeAssistant
        self.pause = ha_client._CONNECT_PAUSE
        ha_client.HomeAssistant = RefusingClient
        ha_client._CONNECT_PAUSE = 0

    def tearDown(self):
        ha_client.HomeAssistant = self.original
        ha_client._CONNECT_PAUSE = self.pause

    def losses(self, error, long_lived=True):
        RefusingClient.error = error
        lost = []

        def on_lost(message, final=False):
            lost.append(final)
            session._stopped = True  # one round is all a test needs

        session = ha_client.Session("http://ha.invalid", LongLived(long_lived),
                                    on_lost=on_lost)
        session._run()
        return lost

    def test_a_rejected_long_lived_token_is_final(self):
        self.assertEqual(self.losses(ha_client.AuthFailed("token rejected")), [True])

    def test_a_refused_login_is_final(self):
        self.assertEqual(self.losses(ha_auth.AuthError("400: invalid_auth"),
                                     long_lived=False), [True])

    def test_a_cancelled_login_is_final(self):
        self.assertEqual(self.losses(ha_auth.AbortedError("login cancelled"),
                                     long_lived=False), [True])

    def test_a_login_token_is_renewed_rather_than_given_up_on(self):
        self.assertEqual(self.losses(ha_client.AuthFailed("token rejected"),
                                     long_lived=False), [False])

    def test_an_unreachable_server_is_tried_again(self):
        self.assertEqual(self.losses(ha_auth.TransportError("Connection refused"),
                                     long_lived=False), [False])
        self.assertEqual(self.losses(ha_client.HomeAssistantError("handshake"),
                                     long_lived=False), [False])


class Urls(unittest.TestCase):
    def test_the_websocket_url_follows_the_scheme(self):
        self.assertEqual(ha_client.websocket_url("https://ha.invalid"),
                         "wss://ha.invalid/api/websocket")
        self.assertEqual(ha_client.websocket_url("http://ha.invalid:8123/"),
                         "ws://ha.invalid:8123/api/websocket")


if __name__ == "__main__":
    unittest.main()
