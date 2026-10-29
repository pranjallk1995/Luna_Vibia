import os
import unittest
from unittest.mock import patch

from sso import LunaSingleSignOn
from config import SSOConfig, UIConfig


class AuthenticationTests(unittest.TestCase):
    def test_verified_allowlisted_email_is_required(self):
        auth = LunaSingleSignOn(frozenset({"owner@example.com"}), SSOConfig(public_url="https://auth.example.com"))
        self.assertTrue(auth.is_allowed({"email": "Owner@Example.com", "email_verified": True}))
        self.assertFalse(auth.is_allowed({"email": "owner@example.com", "email_verified": False}))
        self.assertFalse(auth.is_allowed({"email": "other@example.com", "email_verified": True}))

    def test_allowed_emails_are_required_and_normalized(self):
        with patch.dict(
            os.environ,
            {"LUNA_SSO_URL": "https://auth.example.com", "LUNAVIBIA_API_URL": "http://backend:8000", "LUNAVIBIA_API_TOKEN": "x" * 32},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "LUNAVIBIA_ALLOWED_EMAILS"):
                UIConfig.from_env()
        with patch.dict(
            os.environ,
            {
                "LUNA_SSO_URL": "https://auth.example.com", "LUNAVIBIA_API_URL": "http://backend:8000",
                "LUNAVIBIA_API_TOKEN": "x" * 32,
                "LUNAVIBIA_ALLOWED_EMAILS": " Owner@Example.com ",
            },
            clear=True,
        ):
            self.assertEqual(UIConfig.from_env().allowed_emails, frozenset({"owner@example.com"}))

    def test_api_token_is_required(self):
        with patch.dict(
            os.environ,
            {
                "LUNA_SSO_URL": "https://auth.example.com", "LUNAVIBIA_API_URL": "http://backend:8000",
                "LUNAVIBIA_ALLOWED_EMAILS": "owner@example.com",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "LUNAVIBIA_API_TOKEN"):
                UIConfig.from_env()


class SSOConfigTests(unittest.TestCase):
    def test_public_url_is_required_and_internal_url_has_a_default(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "LUNA_SSO_URL"):
                SSOConfig.from_env()
        with patch.dict(os.environ, {"LUNA_SSO_URL": "https://auth.example.com/"}, clear=True):
            config = SSOConfig.from_env()
        self.assertEqual(config.public_url, "https://auth.example.com")
        self.assertEqual(config.internal_url, "http://luna-sentia-auth:8000")


if __name__ == "__main__":
    unittest.main()
