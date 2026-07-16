"""`EmailNotificationChannel` — a provider-independent SMTP email channel.
Disabled by default; becomes enabled only once real SMTP configuration is
supplied. See docs/31_Notification_Delivery.md "Email Configuration".

`EmailTransport` is an injectable seam (mirrors
`discovery.automatic.verification.PageFetcher`'s own "Protocol + one real
implementation" shape) specifically so the test suite never opens a real
network connection to a real mail server — "Tests must use a fake or local
SMTP adapter. Do not require a real email account for the test suite" (the
mission's own words).

No secret (password, auth token) is ever included in a `NotificationChannelResult`,
a log line, or an exception message raised by this module — see
`_redact()`/`serialize_result()`.
"""

from __future__ import annotations

import os
import smtplib
import time
from email.message import EmailMessage
from typing import Protocol

from src.notifications.base_channel import NotificationChannel
from src.notifications.metadata import NotificationChannelMetadata
from src.notifications.models import NotificationChannelResult, NotificationMessage
from src.notifications.registry import register_notification_channel

_DEFAULT_TIMEOUT_SECONDS = 10.0


class EmailTransport(Protocol):
    def send(
        self, message: EmailMessage, *, host: str, port: int, username: str | None, password: str | None,
        use_tls: bool, use_ssl: bool, timeout: float,
    ) -> None: ...


class SmtplibEmailTransport:
    """The one real `EmailTransport` — a single SMTP session per message, no
    retry of its own (retries are the engine's job, at the delivery level).
    """

    def send(self, message: EmailMessage, *, host: str, port: int, username: str | None, password: str | None,
              use_tls: bool, use_ssl: bool, timeout: float) -> None:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                if use_tls:
                    server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(message)


class EmailNotificationChannel(NotificationChannel):
    channel_name = "email"

    def configure(self, config: dict) -> None:
        super().configure(config)
        self._host = config.get("smtp_host", os.environ.get("SMTP_HOST"))
        self._port = int(config.get("smtp_port", os.environ.get("SMTP_PORT", 587)))
        self._username = config.get("smtp_username", os.environ.get("SMTP_USERNAME"))
        self._password = config.get("smtp_password", os.environ.get("SMTP_PASSWORD"))
        self._sender = config.get("sender_address", os.environ.get("SMTP_SENDER"))
        self._default_recipient = config.get("recipient_address", os.environ.get("SMTP_RECIPIENT"))
        self._use_tls = bool(config.get("use_tls", os.environ.get("SMTP_USE_TLS", "true").lower() == "true"))
        self._use_ssl = bool(config.get("use_ssl", os.environ.get("SMTP_USE_SSL", "false").lower() == "true"))
        self._timeout = float(config.get("timeout", os.environ.get("SMTP_TIMEOUT", _DEFAULT_TIMEOUT_SECONDS)))
        self._transport: EmailTransport = config.get("transport") or SmtplibEmailTransport()

    def validate_configuration(self) -> bool:
        return bool(self._host and self._sender)

    def supports(self, capability: str) -> bool:
        return capability in ("html", "text", "attachments")

    def preview(self, message: NotificationMessage) -> str:
        recipient = message.metadata.get("recipient", self._default_recipient) or "(no recipient configured)"
        return f"To: {recipient}\nFrom: {self._sender or '(not configured)'}\nSubject: {message.subject or ''}\n\n{message.body_text}"

    def send(self, message: NotificationMessage) -> NotificationChannelResult:
        started = time.monotonic()
        if not self.validate_configuration():
            return self._timed_result(self.channel_name, started, success=False, error="Email channel is not configured (missing smtp_host/sender_address)", error_category="invalid_configuration")

        recipient = message.metadata.get("recipient", self._default_recipient)
        if not recipient:
            return self._timed_result(self.channel_name, started, success=False, error="No recipient address available for this message", error_category="invalid_configuration")

        email_message = EmailMessage()
        email_message["Subject"] = message.subject or "Rental Agent Notification"
        email_message["From"] = self._sender
        email_message["To"] = recipient
        email_message.set_content(message.body_text)
        if message.body_html:
            email_message.add_alternative(message.body_html, subtype="html")

        try:
            self._transport.send(
                email_message, host=self._host, port=self._port, username=self._username, password=self._password,
                use_tls=self._use_tls, use_ssl=self._use_ssl, timeout=self._timeout,
            )
        except smtplib.SMTPAuthenticationError as exc:
            return self._timed_result(self.channel_name, started, success=False, error=self._redact(str(exc)), error_category="unauthorized")
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError) as exc:
            return self._timed_result(self.channel_name, started, success=False, error=self._redact(str(exc)), error_category="connection_error")
        except smtplib.SMTPException as exc:
            # Must be checked before the bare `OSError` below: `smtplib.SMTPException`
            # itself subclasses `OSError`, so a plain "mailbox full"-style protocol
            # error would otherwise be miscategorized as a connection_error.
            return self._timed_result(self.channel_name, started, success=False, error=self._redact(str(exc)), error_category="server_error")
        except OSError as exc:
            return self._timed_result(self.channel_name, started, success=False, error=self._redact(str(exc)), error_category="connection_error")

        return self._timed_result(self.channel_name, started, success=True, metadata={"recipient": recipient})

    def channel_info(self) -> NotificationChannelMetadata:
        return NotificationChannelMetadata(
            channel_name=self.channel_name, display_name="Email (SMTP)",
            description="Provider-independent SMTP email delivery — disabled until smtp_host/sender_address are configured.",
            requires_configuration=True, supports_html=True, supports_attachments=False,
        )

    def _redact(self, text: str) -> str:
        """Never let a raw SMTP exception message leak the configured
        password — some SMTP servers echo credentials back in error text.
        """
        if self._password and self._password in text:
            text = text.replace(self._password, "***REDACTED***")
        return text


register_notification_channel(EmailNotificationChannel())
