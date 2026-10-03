"""SMTP delivery tests without a live mail server."""

from types import SimpleNamespace

import pytest

from packages.shared import email as email_module
from packages.shared.email import EmailDeliveryError, send_email


def test_send_email_uses_starttls_and_configured_sender(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def ehlo(self):
            captured["ehlo"] = True

        def starttls(self, context):
            captured["tls_context"] = context

        def login(self, username, password):
            captured["credentials"] = (username, password)

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    settings = SimpleNamespace(
        smtp_host="mail.example.test",
        smtp_port=587,
        smtp_from_email="URDIA <noreply@example.test>",
        smtp_starttls=True,
        smtp_use_ssl=False,
        smtp_username="smtp-user",
        smtp_password="smtp-password",
    )

    send_email(
        settings,
        recipient="person@example.test",
        subject="Verify",
        body="one-time link",
    )

    message = captured["message"]
    assert captured["host"] == "mail.example.test"
    assert captured["tls_context"] is not None
    assert captured["credentials"] == ("smtp-user", "smtp-password")
    assert message["To"] == "person@example.test"
    assert message["From"] == "URDIA <noreply@example.test>"


def test_send_email_requires_smtp_configuration():
    settings = SimpleNamespace(smtp_host=None, smtp_from_email=None)

    with pytest.raises(EmailDeliveryError, match="not configured"):
        send_email(settings, recipient="person@example.test", subject="x", body="y")


def test_send_email_does_not_expose_smtp_exception_text(monkeypatch):
    class FailedSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("private server detail")

    monkeypatch.setattr(email_module.smtplib, "SMTP", FailedSMTP)
    settings = SimpleNamespace(
        smtp_host="mail.example.test",
        smtp_port=587,
        smtp_from_email="noreply@example.test",
        smtp_starttls=True,
        smtp_use_ssl=False,
        smtp_username=None,
        smtp_password="",
    )

    with pytest.raises(EmailDeliveryError) as error:
        send_email(settings, recipient="person@example.test", subject="x", body="y")

    assert "private server detail" not in str(error.value)


def test_send_email_supports_implicit_tls(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout, context):
            captured.update(host=host, port=port, context=context)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def ehlo(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", FakeSMTP)
    settings = SimpleNamespace(
        smtp_host="mail.example.test",
        smtp_port=465,
        smtp_from_email="noreply@example.test",
        smtp_starttls=False,
        smtp_use_ssl=True,
        smtp_username=None,
        smtp_password="",
    )

    send_email(settings, recipient="person@example.test", subject="x", body="y")

    assert captured["port"] == 465
    assert captured["context"] is not None
    assert captured["message"]["To"] == "person@example.test"
