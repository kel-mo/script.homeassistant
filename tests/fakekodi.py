"""Just enough of Kodi's Python modules to import the ones that talk to Kodi.

Everything is a mock, bar what a module needs at import time: the window base
classes, which are subclassed, and the addon's id and path. Strings come from
the English language file, so text reads as it would on screen.
"""

import os
import re
import sys
from unittest import mock

from . import support  # noqa: F401  (puts the addon on the path)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STRINGS = os.path.join(_ROOT, "resources", "language", "resource.language.en_gb",
                        "strings.po")


class _Window:
    def __init__(self, *args, **kwargs):
        pass


def _english():
    with open(_STRINGS, encoding="utf-8") as handle:
        body = handle.read()
    return {int(number): text for number, text
            in re.findall(r'^msgctxt "#(\d+)"\nmsgid "(.*)"$', body, re.M)}


def _install():
    if "xbmc" in sys.modules:
        return
    info = {"id": "script.homeassistant", "path": _ROOT,
            "name": "Home Assistant Dashboard", "icon": ""}
    english = _english()

    xbmc = mock.MagicMock(name="xbmc")
    xbmc.getLanguage.return_value = "en"
    xbmcaddon = mock.MagicMock(name="xbmcaddon")
    xbmcaddon.Addon.return_value.getAddonInfo.side_effect = info.get
    xbmcaddon.Addon.return_value.getLocalizedString.side_effect = \
        lambda string_id: english.get(string_id, "")
    xbmcgui = mock.MagicMock(name="xbmcgui")
    xbmcgui.WindowXML = type("WindowXML", (_Window,), {})
    xbmcgui.WindowXMLDialog = type("WindowXMLDialog", (_Window,), {})
    xbmcvfs = mock.MagicMock(name="xbmcvfs")
    xbmcvfs.translatePath.side_effect = lambda path: path
    sys.modules.update(xbmc=xbmc, xbmcaddon=xbmcaddon, xbmcgui=xbmcgui,
                       xbmcvfs=xbmcvfs)


_install()
