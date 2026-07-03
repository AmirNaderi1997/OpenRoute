import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services.connection_links import build_import_link, build_ws_path, get_connection_details


class ConnectionLinkTests(unittest.TestCase):
    def test_build_ws_path_returns_empty_without_ws_path(self) -> None:
        with patch.object(settings, "VPN_WS_PATH", ""):
            self.assertEqual(build_ws_path("abc-123"), "")

    def test_import_link_uses_direct_public_endpoint(self) -> None:
        with patch.object(settings, "VPN_PUBLIC_HOST", "panel.example.com"), \
             patch.object(settings, "VPN_PUBLIC_PORT", 443):
            link = build_import_link("openroute_1001", "Pass1234", "token-xyz")

        self.assertEqual(link, "ssh://openroute_1001:Pass1234@panel.example.com:443#VPN_openroute_1001")

    def test_connection_details_match_import_link(self) -> None:
        with patch.object(settings, "VPN_PUBLIC_HOST", "panel.example.com"), \
             patch.object(settings, "VPN_PUBLIC_PORT", 8443), \
             patch.object(settings, "VPN_SECURITY", "ssh"):
            details = get_connection_details("user1", "secret1", "tok-1")

        self.assertEqual(details["host"], "panel.example.com")
        self.assertEqual(details["port"], 8443)
        self.assertEqual(details["path"], "")
        self.assertEqual(details["security"], "ssh")
        self.assertEqual(details["type"], "direct")
        self.assertIn("@panel.example.com:8443", str(details["import_link"]))


if __name__ == "__main__":
    unittest.main()
