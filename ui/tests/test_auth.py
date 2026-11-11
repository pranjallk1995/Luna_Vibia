import os
import unittest
from unittest.mock import patch

from config import SSOConfig, UIConfig
from sso import LunaSingleSignOn

ENV = {
    "LUNA_SSO_URL": "https://auth.example.com",
    "LUNAVIBIA_API_TOKEN": "x" * 32,
    "LUNAVIBIA_ALLOWED_EMAILS": " Owner@Example.com ",
}


class AuthenticationTests(unittest.TestCase):

    def test_an_empty_list_lets_only_sentias_owner_in(self):
        auth = LunaSingleSignOn(frozenset(), SSOConfig(public_url="https://auth.example.com"))
        self.assertTrue(auth.is_allowed({"user_id": "owner", "email": "owner@localhost", "email_verified": True}))
        self.assertFalse(auth.is_allowed({"user_id": "u2", "email": "someone@example.com", "email_verified": True}))
        self.assertFalse(auth.is_allowed({"user_id": "owner", "email": "owner@localhost", "email_verified": False}))
    def test_verified_allowlisted_email_is_required(self):
        auth = LunaSingleSignOn(frozenset({"owner@example.com"}), SSOConfig(public_url="https://auth.example.com"))
        self.assertTrue(auth.is_allowed({"email": "Owner@Example.com", "email_verified": True}))
        self.assertFalse(auth.is_allowed({"email": "owner@example.com", "email_verified": False}))
        self.assertFalse(auth.is_allowed({"email": "other@example.com", "email_verified": True}))

    def test_allowed_emails_are_normalized(self):
        with patch.dict(os.environ, ENV, clear=True):
            self.assertEqual(UIConfig.from_env().allowed_emails, frozenset({"owner@example.com"}))

    def test_settings_are_required(self):
        # Every setting but the allowed emails, which default to Sentia's owner only.
        for name in (key for key in ENV if key != "LUNAVIBIA_ALLOWED_EMAILS"):
            env = {key: value for key, value in ENV.items() if key != name}
            with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(RuntimeError, name):
                UIConfig.from_env()


if __name__ == "__main__":
    unittest.main()
