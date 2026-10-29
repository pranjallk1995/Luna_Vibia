"""Tests for Hidden Vault credentials and sessions."""

import unittest

from fakes import FakeCredentialRepository

from app.transport.security import CredentialPolicy, HiddenVaultAuth, SessionStore


class HiddenVaultAuthTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeCredentialRepository()
        self.auth = HiddenVaultAuth(
            self.repository, CredentialPolicy(iterations=100_000), SessionStore(30 * 60)
        )

    def test_setup_login_and_session(self):
        token = self.auth.setup("strong-password", "12345678")
        self.auth.require(token)
        self.auth.logout(token)
        with self.assertRaises(PermissionError):
            self.auth.require(token)
        self.auth.require(self.auth.login("strong-password"))

    def test_setup_only_once(self):
        self.auth.setup("strong-password", "12345678")
        with self.assertRaisesRegex(ValueError, "already been created"):
            self.auth.setup("other-password", "87654321")

    def test_pin_must_be_exactly_eight_digits(self):
        for pin in ("1234567", "123456789", "abcdefgh"):
            with self.assertRaises(ValueError):
                self.auth.setup("strong-password", pin)

    def test_reset_requires_pin_and_replaces_password(self):
        old_token = self.auth.setup("old-password", "12345678")
        with self.assertRaises(PermissionError):
            self.auth.reset("87654321", "new-password")
        token = self.auth.reset("12345678", "new-password")
        self.auth.require(token)
        with self.assertRaises(PermissionError):
            self.auth.require(old_token)
        with self.assertRaises(PermissionError):
            self.auth.login("old-password")
        self.auth.require(self.auth.login("new-password"))


if __name__ == "__main__":
    unittest.main()
