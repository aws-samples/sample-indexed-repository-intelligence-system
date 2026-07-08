# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from bedrock_agentcore.memory import MemoryClient
from strands.hooks import (
    AgentInitializedEvent,
    HookProvider,
    HookRegistry,
    MessageAddedEvent,
)
import logging
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MemoryHookProvider(HookProvider):
    def __init__(
        self,
        memory_client: MemoryClient,
        memory_id_getter,
        actor_id: str,
        session_id: str,
    ):
        """
        Initialize the MemoryHookProvider

        Args:
            memory_client: The memory client to use
            memory_id_getter: A function that returns the current memory_id
            actor_id: The actor ID
            session_id: The session ID
        """
        self.memory_client = memory_client
        self.memory_id_getter = memory_id_getter
        self.actor_id = actor_id
        self.session_id = session_id

    @property
    def memory_id(self):
        """Dynamically get the current memory_id"""
        return self.memory_id_getter()

    def on_agent_initialized(self, event: AgentInitializedEvent):
        """Load recent conversation history when agent starts"""
        try:
            # Load the last 5 conversation turns from memory
            recent_turns = self.memory_client.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=self.session_id,
                k=20,
            )

            if recent_turns:
                # Format conversation history for context
                context_messages = []
                for turn in recent_turns:
                    for message in turn:
                        role = message["role"]
                        content = message["content"]["text"]
                        context_messages.append(f"{role}: {content}")

                context = "\n".join(context_messages)
                # Add context to agent's system prompt.
                event.agent.system_prompt += f"\n\nRecent conversation:\n{context}"
                logger.info(
                    f"✅ Memory load Loaded {len(recent_turns)} conversation turns"
                )
                logger.info(f"✅ Memory load Loaded conversations: {recent_turns}")

        except Exception as e:
            logger.error(f"logging: memory_id = {self.memory_id}")
            logger.error(f"Memory load error: {e}")
            logger.error(f"Memory load Traceback: {traceback.format_exc()}")

    def on_message_added(self, event: MessageAddedEvent):
        """Store messages in memory"""
        messages = event.agent.messages

        # Extract message content and role
        message_str = str(messages[-1].get("content", ""))
        message_role = messages[-1]["role"]

        # Calculate message size
        size_bytes = len(message_str.encode("utf-8"))
        size_kb = size_bytes / 1024
        logger.info(
            f"Memory add Message size: {size_bytes} bytes ({size_kb:.2f} KB), ROLE: {message_role}"
        )

        # Check if message is larger than 8.5KB
        max_size_bytes = 8.5 * 1024  # 8.5KB in bytes
        try:
            if size_bytes > max_size_bytes:
                # Truncate the message
                logger.info("Memory add Message too large, truncating")
                truncated_message = f"This message was too large to add. Here is the trunchated head: {message_str[:500]}"

                try:
                    # Store the truncated message
                    self.memory_client.create_event(
                        memory_id=self.memory_id,
                        actor_id=self.actor_id,
                        session_id=self.session_id,
                        messages=[(truncated_message, message_role)],
                    )
                    logger.info("Successfully stored truncated message")
                except Exception as e:
                    logger.error(f"Memory add logging: memory_id = {self.memory_id}")
                    logger.error(f"Memory add Failed to store truncated message: {e}")
            else:
                try:
                    # Store the original message
                    self.memory_client.create_event(
                        memory_id=self.memory_id,
                        actor_id=self.actor_id,
                        session_id=self.session_id,
                        messages=[(message_str, message_role)],
                    )
                except Exception as e:
                    logger.error(f"Memory add logging: memory_id = {self.memory_id}")
                    logger.error(f"Memory add Memory save error: {e}")
        except Exception as e:
            logger.error(f"Memory add Error: {e}")
            logger.error(f"Memory add Traceback: {traceback.format_exc()}")

    def register_hooks(self, registry: HookRegistry):
        # Register memory hooks
        registry.add_callback(MessageAddedEvent, self.on_message_added)
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
