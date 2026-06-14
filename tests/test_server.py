from unittest.mock import patch

from fastapi.testclient import TestClient

import server


client = TestClient(server.app)


def test_root_lists_send_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    paths = {tool["path"] for tool in response.json()["tools"]}
    assert "/send_email" in paths


def test_send_email_endpoint_returns_message_id():
    with patch.object(server, "APPROVAL_MODE", "auto"):
        with patch.object(
            server,
            "send_email",
            return_value={
                "status": "ok",
                "message_id": "message-123",
                "thread_id": "thread-123",
            },
        ):
            response = client.post(
                "/send_email",
                json={
                    "to": "person@example.com",
                    "subject": "Subject",
                    "body": "Report body",
                },
            )

    assert response.status_code == 200
    assert response.json()["message_id"] == "message-123"
