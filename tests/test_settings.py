"""The settings file, as Kodi will draw it."""

import os
import unittest
import xml.etree.ElementTree as ElementTree

from . import support  # noqa: F401  (puts the addon on the path)

SETTINGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "resources", "settings.xml")


class Secrets(unittest.TestCase):
    def test_what_opens_home_assistant_is_not_shown_on_screen(self):
        root = ElementTree.parse(SETTINGS).getroot()
        for setting_id in ("password", "token"):
            setting = root.find(".//setting[@id='%s']" % setting_id)
            self.assertEqual(setting.findtext("control/hidden"), "true", setting_id)


if __name__ == "__main__":
    unittest.main()
