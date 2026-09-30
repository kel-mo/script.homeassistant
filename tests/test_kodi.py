"""What the addon hands Kodi to fetch."""

import unittest

from . import fakekodi  # noqa: F401  (stands in for Kodi's modules)
from resources.lib import kodi

BASE = "https://ha.example.com"


class ImageUrls(unittest.TestCase):
    def test_a_path_of_home_assistant_carries_the_token(self):
        self.assertEqual(kodi.image_url(BASE, "/api/image_proxy/x", "secret"),
                         BASE + "/api/image_proxy/x|Authorization=Bearer secret")

    def test_so_does_a_full_address_on_the_same_server(self):
        self.assertEqual(
            kodi.image_url(BASE, "https://HA.example.com:443/api/x", "secret"),
            "https://HA.example.com:443/api/x|Authorization=Bearer secret")

    def test_another_server_never_sees_it(self):
        for url in ("https://cdn.example.org/api/cover.jpg",
                    "http://ha.example.com/api/x",
                    "https://ha.example.com:8443/api/x",
                    "https://ha.example.com.evil.invalid/api/x"):
            self.assertEqual(kodi.image_url(BASE, url, "secret"), url)

    def test_a_path_outside_the_api_goes_without(self):
        self.assertEqual(kodi.image_url(BASE, "/local/cover.jpg", "secret"),
                         BASE + "/local/cover.jpg")


if __name__ == "__main__":
    unittest.main()
