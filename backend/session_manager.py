# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Session Manager for WebSocket Chatbot Backend

This module manages active WebSocket sessions, maintaining a hashmap (dictionary)
of chatbot objects for each connected client.
"""

import uuid
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

# We'll import the Agent class from your existing IRIS system
from iris.agentic_chat import Agent
from iris.utils.utils import load_default_config

try:
    from .create_backend_agent import create_backend_agent
except ImportError:
    from create_backend_agent import create_backend_agent

log = logging.getLogger(__name__)


@dataclass
class ChatbotSession:
    """
    Represents a single chatbot session for a WebSocket connection.

    Each session contains:
    - session_id: Unique identifier for this session
    - agent: The AI agent instance for this session
    - created_at: When this session was created
    - last_activity: Last time this session was used
    - user_info: User information from JWT token (optional)
    """

    session_id: str
    agent: Agent
    created_at: datetime
    last_activity: datetime
    user_info: Optional[Dict[str, str]] = None

    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = datetime.now()


class SessionManager:
    """
    Manages active WebSocket sessions using a simple hashmap.

    This class provides:
    1. Session creation with unique IDs
    2. Session retrieval by ID
    3. Session cleanup when clients disconnect
    4. Agent initialization for each session
    """

    _MAX_SESSIONS = 100
    _SESSION_TTL = timedelta(hours=1)

    def __init__(self):
        # The hashmap - this is our core data structure
        # Key: session_id (string), Value: ChatbotSession object
        self._sessions: Dict[str, ChatbotSession] = {}

        # Load configuration for AI agent setup
        self.config = load_default_config()

        log.info("SessionManager initialized")

    def _evict_expired(self) -> None:
        """Remove sessions that have been idle beyond TTL."""
        now = datetime.now()
        expired = [
            sid
            for sid, s in self._sessions.items()
            if (now - s.last_activity) > self._SESSION_TTL
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            log.info(
                f"Evicted {len(expired)} expired session(s). Remaining: {len(self._sessions)}"
            )

    def create_session(self, user_info: Optional[Dict[str, str]] = None) -> str:
        """
        Create a new chatbot session.

        This method:
        1. Generates a unique session ID
        2. Initializes a new AI Agent instance
        3. Creates a ChatbotSession object
        4. Stores it in the hashmap
        5. Returns the session ID

        Returns:
            str: The unique session ID
        """
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        return self.create_session_with_id(session_id, user_info)

    def create_session_with_id(
        self, session_id: str, user_info: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Create a new chatbot session with a specific session ID.

        Args:
            session_id: The session ID to use
            user_info: Optional user information

        Returns:
            str: The session ID
        """
        log.info(f"Creating new session: {session_id}")

        self._evict_expired()

        if len(self._sessions) >= self._MAX_SESSIONS:
            raise RuntimeError(
                f"Session limit reached ({self._MAX_SESSIONS}). Try again later."
            )

        try:
            # Initialize AI agent for this session
            agent = self._create_agent()

            # Create session object
            session = ChatbotSession(
                session_id=session_id,
                agent=agent,
                created_at=datetime.now(),
                last_activity=datetime.now(),
                user_info=user_info,
            )

            # Store in hashmap
            self._sessions[session_id] = session

            log.info(
                f"Session {session_id} created successfully. Total sessions: {len(self._sessions)}"
            )
            return session_id

        except Exception as e:
            log.error(f"Failed to create session {session_id}: {str(e)}")
            raise

    def get_session(self, session_id: str) -> Optional[ChatbotSession]:
        """
        Retrieve a session by ID.

        Args:
            session_id: The session ID to look up

        Returns:
            ChatbotSession if found, None otherwise
        """
        session = self._sessions.get(session_id)
        if session:
            session.update_activity()
            log.debug(f"Retrieved session {session_id}")
        else:
            log.warning(f"Session {session_id} not found")

        return session

    def remove_session(self, session_id: str) -> bool:
        """
        Remove a session from the hashmap (cleanup on disconnect).

        Args:
            session_id: The session ID to remove

        Returns:
            bool: True if session was removed, False if not found
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            log.info(
                f"Session {session_id} removed. Remaining sessions: {len(self._sessions)}"
            )
            return True
        else:
            log.warning(f"Attempted to remove non-existent session: {session_id}")
            return False

    def get_active_session_count(self) -> int:
        """Get the number of active sessions"""
        return len(self._sessions)

    def list_sessions(self) -> Dict[str, dict]:
        """
        Get information about all active sessions (for debugging/monitoring).

        Returns:
            Dict with session info
        """
        return {
            session_id: {
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
                "active_duration": str(datetime.now() - session.created_at),
            }
            for session_id, session in self._sessions.items()
        }

    def _create_agent(self) -> Agent:
        """
        Create and configure an AI Agent instance for a new session.

        This uses the centralized create_backend_agent function which reuses
        components from the iris package for easier maintenance.

        Returns:
            Agent: Configured AI agent instance
        """
        try:
            # Use the backend agent creation function
            agent = create_backend_agent()
            log.debug("Agent created successfully using create_backend_agent")
            return agent

        except Exception as e:
            log.error(f"Failed to create agent: {str(e)}")
            raise


# Global session manager instance
# This will be imported by the WebSocket server
session_manager = SessionManager()
