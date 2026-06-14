from unittest.mock import MagicMock, patch

import pytest

from gmail_tool import create_email_draft, send_email


def _gmail_service():
    service = MagicMock()
    service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {
        "id": "draft-123"
    }
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "message-123",
        "threadId": "thread-123",
    }
    return service


def test_create_email_draft_uses_drafts_api():
    service = _gmail_service()
    with patch("gmail_tool.get_credentials", return_value=MagicMock()):
        with patch("gmail_tool.build", return_value=service):
            result = create_email_draft("person@example.com", "Subject", "# Report")

    assert result == {"status": "ok", "draft_id": "draft-123"}
    service.users.return_value.drafts.return_value.create.assert_called_once()
    service.users.return_value.messages.return_value.send.assert_not_called()


def test_send_email_uses_messages_send_api():
    service = _gmail_service()
    with patch("gmail_tool.get_credentials", return_value=MagicMock()):
        with patch("gmail_tool.build", return_value=service):
            result = send_email("person@example.com", "Subject", "# Report")

    assert result == {
        "status": "ok",
        "message_id": "message-123",
        "thread_id": "thread-123",
    }
    service.users.return_value.messages.return_value.send.assert_called_once()
    service.users.return_value.drafts.return_value.create.assert_not_called()


@pytest.mark.parametrize("operation", [create_email_draft, send_email])
def test_email_operations_reject_invalid_recipient(operation):
    with pytest.raises(ValueError, match="Invalid email address"):
        operation("not-an-email", "Subject", "Body")
