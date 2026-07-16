"""`NotificationChannelRegistry`/`NotificationChannelFactory` — self-
registration, enabled-vs-registered distinction, and the "future channels
never touch NotificationEngine" contract (a fake channel registers itself
exactly like a real one).
"""

from __future__ import annotations

import unittest

from src.notifications.base_channel import NotificationChannel
from src.notifications.exceptions import NotificationConfigurationError
from src.notifications.factory import NotificationChannelFactory
from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import NotificationChannelResult
from src.notifications.registry import NotificationChannelRegistry, register_notification_channel


class _FakeChannel(NotificationChannel):
    channel_name = "fake_test_channel"

    def configure(self, config: dict) -> None:
        super().configure(config)
        self._enabled = bool(config.get("enabled", False))

    def validate_configuration(self) -> bool:
        return self._enabled

    def supports(self, capability: str) -> bool:
        return capability == "text"

    def preview(self, message) -> str:
        return message.body_text

    def send(self, message) -> NotificationChannelResult:
        return NotificationChannelResult(channel=self.channel_name, success=True)

    def channel_info(self) -> NotificationChannelMetadata:
        return NotificationChannelMetadata(channel_name=self.channel_name, display_name="Fake", description="test-only", requires_configuration=True, supports_html=False, supports_attachments=False)


class NotificationChannelRegistryTests(unittest.TestCase):
    def test_real_channels_self_register_on_import(self) -> None:
        self.assertTrue(NotificationChannelRegistry.is_registered("console"))
        self.assertTrue(NotificationChannelRegistry.is_registered("file"))
        self.assertTrue(NotificationChannelRegistry.is_registered("email"))
        self.assertTrue(NotificationChannelRegistry.is_registered("webhook"))

    def test_console_and_file_are_enabled_with_zero_configuration(self) -> None:
        enabled_names = {c.channel_name for c in NotificationChannelRegistry.enabled()}
        self.assertIn("console", enabled_names)
        self.assertIn("file", enabled_names)

    def test_email_and_webhook_are_disabled_until_configured(self) -> None:
        enabled_names = {c.channel_name for c in NotificationChannelRegistry.enabled()}
        self.assertNotIn("email", enabled_names)
        self.assertNotIn("webhook", enabled_names)

    def test_a_new_channel_can_register_without_any_engine_code_change(self) -> None:
        register_notification_channel(_FakeChannel({"enabled": True}))
        try:
            self.assertTrue(NotificationChannelRegistry.is_registered("fake_test_channel"))
            self.assertIn("fake_test_channel", {c.channel_name for c in NotificationChannelRegistry.enabled()})
            resolved = NotificationChannelFactory.get("fake_test_channel")
            self.assertIs(resolved, NotificationChannelRegistry.get("fake_test_channel"))
        finally:
            NotificationChannelRegistry._channels.pop("fake_test_channel", None)

    def test_registering_a_non_channel_object_raises(self) -> None:
        with self.assertRaises(NotificationConfigurationError):
            register_notification_channel(object())  # type: ignore[arg-type]

    def test_unknown_channel_name_raises_a_clear_error(self) -> None:
        with self.assertRaises(NotificationConfigurationError):
            NotificationChannelFactory.get("does_not_exist")

    def test_resolve_none_returns_every_enabled_channel(self) -> None:
        resolved_names = {c.channel_name for c in NotificationChannelFactory.resolve(None)}
        self.assertEqual(resolved_names, {c.channel_name for c in NotificationChannelRegistry.enabled()})

    def test_resolve_explicit_names_returns_exactly_those_regardless_of_enabled_state(self) -> None:
        resolved = NotificationChannelFactory.resolve(["console", "email"])
        self.assertEqual([c.channel_name for c in resolved], ["console", "email"])


if __name__ == "__main__":
    unittest.main()
