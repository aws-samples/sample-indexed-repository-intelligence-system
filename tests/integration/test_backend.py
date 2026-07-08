# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Tests for backend WebSocket server and authentication.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Ensure backend is importable
backend_path = Path(__file__).parent.parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))


@pytest.mark.unit
class TestAuthModule:
    """Test authentication module."""

    @patch("backend.auth.os.getenv")
    def test_cognito_auth_disabled_without_config(self, mock_getenv):
        """Test auth is disabled without Cognito config."""
        mock_getenv.side_effect = lambda k, d="": ""
        from backend.auth import CognitoJWTAuth

        auth = CognitoJWTAuth()
        assert not auth.enabled

    @patch("backend.auth.os.getenv")
    def test_cognito_auth_enabled_with_config(self, mock_getenv):
        """Test auth is enabled with Cognito config."""

        def getenv_side_effect(key, default=""):
            config = {
                "AWS_DEFAULT_REGION": "us-east-1",
                "USER_POOL_ID": "us-east-1_test",
                "USER_POOL_CLIENT_ID": "test-client-id",
            }
            return config.get(key, default)

        mock_getenv.side_effect = getenv_side_effect

        with patch("backend.auth.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"keys": []}
            from backend.auth import CognitoJWTAuth

            auth = CognitoJWTAuth()
            assert auth.enabled
            assert auth.region == "us-east-1"

    def test_verify_token_disabled_auth(self):
        """Test token verification when auth is disabled."""
        from backend.auth import cognito_auth

        original_enabled = cognito_auth.enabled
        try:
            cognito_auth.enabled = False
            result = cognito_auth.verify_token("fake-token")
            assert result is not None
            assert "sub" in result
        finally:
            cognito_auth.enabled = original_enabled


@pytest.mark.unit
class TestSessionManager:
    """Test session manager."""

    @patch("create_backend_agent.create_backend_agent")
    def test_create_session(self, mock_create_agent):
        """Test session creation."""
        from session_manager import SessionManager

        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent

        manager = SessionManager()

        session_id = manager.create_session()
        assert session_id is not None
        assert manager.get_active_session_count() == 1

    @patch("create_backend_agent.create_backend_agent")
    def test_get_session(self, mock_create_agent):
        """Test session retrieval."""
        from session_manager import SessionManager

        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent

        manager = SessionManager()

        session_id = manager.create_session()
        session = manager.get_session(session_id)

        assert session is not None
        assert session.session_id == session_id

    @patch("create_backend_agent.create_backend_agent")
    def test_remove_session(self, mock_create_agent):
        """Test session removal."""
        from session_manager import SessionManager

        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent

        manager = SessionManager()

        session_id = manager.create_session()
        assert manager.remove_session(session_id)
        assert manager.get_active_session_count() == 0


@pytest.mark.unit
class TestWebSocketServer:
    """Test WebSocket server components."""

    def test_connection_manager_init(self):
        """Test ConnectionManager initialization."""
        from websocket_server import ConnectionManager

        manager = ConnectionManager()
        assert len(manager.active_connections) == 0
        assert len(manager.authenticated_connections) == 0

    def test_connection_manager_disconnect(self):
        """Test WebSocket disconnection."""
        from websocket_server import ConnectionManager

        manager = ConnectionManager()
        mock_websocket = Mock()
        manager.active_connections[mock_websocket] = "test-session"

        with patch("session_manager.session_manager.remove_session"):
            manager.disconnect(mock_websocket)

            assert mock_websocket not in manager.active_connections

    def test_websocket_message_model(self):
        """Test WebSocketMessage model."""
        from websocket_server import WebSocketMessage

        msg = WebSocketMessage(type="test", data={"key": "value"})

        assert msg.type == "test"
        assert msg.data == {"key": "value"}
        assert msg.message_id is None


@pytest.mark.integration
class TestWebSocketEndpoints:
    """Test WebSocket endpoints with TestClient."""

    def test_health_endpoint(self):
        """Test health check endpoint."""
        from websocket_server import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"

    def test_config_endpoint(self):
        """Test config endpoint."""
        from websocket_server import app

        client = TestClient(app)
        response = client.get("/config")

        assert response.status_code == 200
        data = response.json()
        assert "codebase_dir" in data
        assert "status" in data

    def test_sessions_endpoint(self):
        """Test sessions endpoint."""
        from websocket_server import app

        client = TestClient(app)
        response = client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert "total_count" in data


@pytest.mark.integration
class TestWebSocketConnection:
    """Test WebSocket connection flow."""

    def test_websocket_ping_pong(self):
        """Test WebSocket ping/pong using TestClient."""
        from websocket_server import app

        client = TestClient(app)

        with client.websocket_connect("/ws") as websocket:
            # Receive welcome message
            data = websocket.receive_json()
            assert data["type"] == "welcome"
            assert "session_id" in data["data"]

            # Receive ready message
            ready = websocket.receive_json()
            assert ready["type"] == "ready"

            # Test ping/pong
            websocket.send_json({"type": "ping"})
            response = websocket.receive_json()
            assert response["type"] == "pong"
