# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Monitoring and callback system for tracking Strands agent execution in IDP.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import (
    AfterInvocationEvent,
    AgentInitializedEvent,
    BeforeInvocationEvent,
    MessageAddedEvent,
)
from ..utils.cache_metrics import CacheMetrics

# Try to import production events (new names) or fall back to experimental
try:
    from strands.hooks import (
        AfterModelCallEvent,
        AfterToolCallEvent,
        BeforeModelCallEvent,
        BeforeToolCallEvent,
    )

    EXPERIMENTAL_EVENTS_AVAILABLE = True
except ImportError:
    EXPERIMENTAL_EVENTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class AgentMonitor(HookProvider):
    """
    Comprehensive monitoring hook provider for Strands agents.

    This class provides detailed tracking of agent execution including:
    - Message flow monitoring (MessageAddedEvent)
    - Tool invocation tracking
    - Model invocation tracking
    - Request lifecycle monitoring
    """

    def __init__(
        self,
        log_level: int = logging.INFO,
        enable_detailed_logging: bool = True,
        throttling_callback=None,
        include_debug_tool_output: bool = False,
        log_file_path: Optional[str] = None,
        console_truncate_length: int = 100,
        agent_name: str = "agent",
    ):
        """
        Initialize the agent monitor.

        Args:
            log_level: Logging level for monitor output
            enable_detailed_logging: Whether to log detailed event information
            throttling_callback: Optional callback function to call when throttling is detected
            include_debug_tool_output: Whether to include debug_tool_output in tool result messages
            log_file_path: Path to write full JSON logs (None to disable file logging)
            console_truncate_length: Maximum length of log messages in console output
        """
        self.log_level = log_level
        self.enable_detailed_logging = enable_detailed_logging
        self.throttling_callback = throttling_callback
        self.include_debug_tool_output = include_debug_tool_output
        self.console_truncate_length = console_truncate_length

        # Set up file logging if path is provided
        self.log_file_path = log_file_path
        if log_file_path:
            # Create directory if it doesn't exist
            log_dir = os.path.dirname(log_file_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
        self.execution_stats = {
            "messages_added": 0,
            "tool_invocations": 0,
            "model_invocations": 0,
            "requests_processed": 0,
            "start_time": None,
            "end_time": None,
        }
        self.message_history: List[Dict[str, Any]] = []
        self.tool_history: List[Dict[str, Any]] = []
        self.model_history: List[Dict[str, Any]] = []
        self.cache_metrics = CacheMetrics()

        # Set up logger for this monitor
        self.monitor_logger = logging.getLogger(f"{__name__}.AgentMonitor.{agent_name}")
        self.monitor_logger.setLevel(log_level)

        # Initialize log file if path is provided
        if self.log_file_path:
            self._write_to_log_file(
                {
                    "event": "monitor_initialized",
                    "timestamp": datetime.now().isoformat(),
                }
            )

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register all monitoring callbacks with the hook registry."""
        # Core events
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(BeforeInvocationEvent, self.on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self.on_after_invocation)
        registry.add_callback(MessageAddedEvent, self.on_message_added)

        # Experimental events (if available)
        if EXPERIMENTAL_EVENTS_AVAILABLE:
            print("\n\n REGISTERING EXPERIMENTAL HOOKS \n\n")
            registry.add_callback(BeforeToolCallEvent, self.on_before_tool_invocation)
            registry.add_callback(AfterToolCallEvent, self.on_after_tool_invocation)
            registry.add_callback(BeforeModelCallEvent, self.on_before_model_invocation)
            registry.add_callback(AfterModelCallEvent, self.on_after_model_invocation)
        else:
            self.monitor_logger.warning(
                "Experimental events not available - tool and model monitoring disabled"
            )

    def on_agent_initialized(self, event: AgentInitializedEvent) -> None:
        """Handle agent initialization event."""
        self.monitor_logger.info("🤖 Agent initialized and ready")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Agent details: {event.agent}")

    def on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        """Handle request start event."""
        self.execution_stats["start_time"] = datetime.now()
        self.execution_stats["requests_processed"] += 1

        self.monitor_logger.info("🚀 Starting new agent request")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Request details: Agent={event.agent}")

    def on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Handle request completion event."""
        self.execution_stats["end_time"] = datetime.now()

        if self.execution_stats["start_time"]:
            duration = (
                self.execution_stats["end_time"] - self.execution_stats["start_time"]
            )
            self.monitor_logger.info(
                f"✅ Agent request completed in {duration.total_seconds():.2f}s"
            )
        else:
            self.monitor_logger.info("✅ Agent request completed")

        # Log execution summary
        self.log_execution_summary()

        # Write full execution report to log file
        if self.log_file_path:
            self._write_to_log_file(
                {
                    "event": "execution_completed",
                    "timestamp": datetime.now().isoformat(),
                    "report": self.get_execution_report(),
                }
            )

    def on_message_added(self, event: MessageAddedEvent) -> None:
        """
        Handle message added event - this is the main event requested for monitoring.

        This callback tracks all messages added to the agent's conversation history,
        including user messages, assistant responses, and tool results.
        """
        self.execution_stats["messages_added"] += 1

        message = event.message
        message_info = {
            "timestamp": datetime.now().isoformat(),
            **self._get_message_preview(message),
        }

        self.message_history.append(message_info)

        # Log the message event
        role = message_info["role"]
        content = message_info["content"]

        # Create truncated preview for console
        content_str = str(content)
        if len(content_str) > self.console_truncate_length:
            content_preview = f"{content_str[: self.console_truncate_length]}... (truncated, full log in file)"
        else:
            content_preview = content_str

        self.monitor_logger.info(f"💬 Message added: [{role}] {content_preview}")

        # Write full message to log file
        if self.log_file_path:
            self._write_to_log_file(
                {
                    "event": "message_added",
                    "timestamp": datetime.now().isoformat(),
                    "message": message_info,
                }
            )

        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Full message details: {message}")

    def on_before_tool_invocation(self, event) -> None:
        """Handle before tool invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        tool_name = event.tool_use.get("name", "unknown")
        tool_input = event.tool_use.get("input", {})

        # Create truncated preview for console
        event_str = str(event)
        if len(event_str) > self.console_truncate_length:
            event_preview = f"{event_str[: self.console_truncate_length]}... (truncated, full log in file)"
        else:
            event_preview = event_str

        self.monitor_logger.info(f"🔧 Invoking tool: {tool_name} --> {event_preview}")

        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Tool input: {json.dumps(tool_input, indent=2)}")

        # Write full tool invocation to log file
        if self.log_file_path:
            self._write_to_log_file(
                {
                    "event": "tool_invocation_started",
                    "timestamp": datetime.now().isoformat(),
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                }
            )

    def on_after_tool_invocation(self, event) -> None:
        """Handle after tool invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        self.execution_stats["tool_invocations"] += 1

        tool_name = event.tool_use.get("name", "unknown")
        result_preview = self._get_tool_result_preview(event.result)

        # Log tool result token size for context tracking
        try:
            from ..utils.bedrock import estimate_tokens

            result_str = str(event.result) if event.result is not None else ""
            result_tokens = estimate_tokens(result_str)
            self.monitor_logger.info(
                f"📊 Tool '{tool_name}' result: {len(result_str)} chars, ~{result_tokens} tokens"
            )
        except Exception:
            pass

        tool_info = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "result_preview": result_preview,
        }

        self.tool_history.append(tool_info)

        # Create truncated preview for console
        preview_str = str(result_preview)
        if len(preview_str) > self.console_truncate_length:
            truncated_preview = f"{preview_str[: self.console_truncate_length]}... (truncated, full log in file)"
        else:
            truncated_preview = preview_str

        self.monitor_logger.info(
            f"✅ Tool completed: {tool_name} -> {truncated_preview}"
        )

        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Full tool result: {event.result}")

        # Write full tool result to log file
        if self.log_file_path:
            self._write_to_log_file(
                {
                    "event": "tool_invocation_completed",
                    "timestamp": datetime.now().isoformat(),
                    "tool_name": tool_name,
                    "tool_result": self._safe_json_serialize(event.result),
                }
            )

    def on_before_model_invocation(self, event) -> None:
        """Handle before model invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        self.monitor_logger.info("🧠 Invoking language model")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Model invocation details: {event}")

    def on_after_model_invocation(self, event) -> None:
        """Handle after model invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        self.execution_stats["model_invocations"] += 1

        model_info = {
            "timestamp": datetime.now().isoformat(),
        }

        # Check for throttling exceptions
        if event.exception:
            self._handle_model_exception(event.exception)

        # Record cache metrics if available
        if hasattr(event, "response") and event.response:
            response = event.response
            if isinstance(response, dict) and "usage" in response:
                self.cache_metrics.record_response(response)

        self.model_history.append(model_info)

        self.monitor_logger.info("✅ Model invocation completed")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Model response details: {event}")

    def _handle_model_exception(self, exception: Exception) -> None:
        """Handle exceptions from model invocations, particularly throttling errors."""
        from botocore.exceptions import ClientError

        # Check for throttling patterns in the exception string first
        exception_str = str(exception)
        throttling_patterns = [
            "ThrottlingException",
            "ModelThrottledException",
            "ServiceQuotaExceededException",
            "RequestLimitExceeded",
            "Too many requests",
            "throttl",  # catch variations of throttling
        ]

        is_throttling = any(
            pattern.lower() in exception_str.lower() for pattern in throttling_patterns
        )

        if isinstance(exception, ClientError):
            error_code = exception.response.get("Error", {}).get("Code", "")
            error_message = exception.response.get("Error", {}).get("Message", "")

            # Check if this is a throttling-related error
            throttling_errors = [
                "ThrottlingException",
                "ModelThrottledException",
                "ServiceQuotaExceededException",
                "RequestLimitExceeded",
            ]

            if error_code in throttling_errors:
                self.monitor_logger.error(
                    f"❌ Model invocation error: {error_code} - {error_message}"
                )

                # Call throttling callback if provided
                if self.throttling_callback:
                    try:
                        self.throttling_callback(exception)
                    except Exception as e:
                        self.monitor_logger.error(f"Error in throttling callback: {e}")
            else:
                self.monitor_logger.error(
                    f"❌ Model invocation error: {error_code} - {error_message}"
                )
        elif is_throttling:
            # Handle non-ClientError throttling exceptions (like ModelThrottledException)
            self.monitor_logger.error(
                f"❌ Model invocation error: {type(exception).__name__} - {str(exception)}"
            )

            # Call throttling callback if provided
            if self.throttling_callback:
                try:
                    self.throttling_callback(exception)
                except Exception as e:
                    self.monitor_logger.error(f"Error in throttling callback: {e}")
        else:
            self.monitor_logger.error(
                f"❌ Model invocation error: {type(exception).__name__} - {str(exception)}"
            )

    def _get_message_preview(self, message) -> Dict[str, Any]:
        """Get message content and metadata for logging."""

        # Example message: message={'role': 'user', 'content': [{'text': 'How many documents have I processed each day?'}]}
        try:
            content = message["content"]
            role = message["role"]

            # Special case for tool result messages
            if role == "user":
                for c in message["content"]:
                    if "toolResult" in c:
                        tool_result = c["toolResult"]
                        framework_status = tool_result.get("status", "unknown")

                        # Try to parse the actual tool response to determine real success/failure
                        actual_status = framework_status
                        try:
                            # Check if the tool result content contains success/failure information
                            content_list = tool_result.get("content", [])
                            if content_list and isinstance(content_list, list):
                                for content_item in content_list:
                                    if (
                                        isinstance(content_item, dict)
                                        and "text" in content_item
                                    ):
                                        import json

                                        try:
                                            # Try to parse the text as JSON to check for success field
                                            parsed_content = json.loads(
                                                content_item["text"]
                                            )
                                            if (
                                                isinstance(parsed_content, dict)
                                                and "success" in parsed_content
                                            ):
                                                # Override the framework status with the actual tool result
                                                actual_status = (
                                                    "success"
                                                    if parsed_content["success"]
                                                    else "error"
                                                )
                                                break
                                        except (json.JSONDecodeError, TypeError):
                                            # If parsing fails, stick with framework status
                                            pass
                        except Exception:
                            # If any error occurs in parsing, use framework status
                            pass

                        res = {
                            "role": "tool",
                            "content": f"Tool completed with status '{actual_status}'.",
                            "message_type": type(message).__name__,
                        }

                        # Only include debug_tool_output if the flag is enabled
                        if self.include_debug_tool_output:
                            res["debug_tool_output"] = tool_result

                        if self.enable_detailed_logging:
                            self.monitor_logger.debug(f"Full tool use output: {res}")
                        return res

            # For all other user/assistant messages, return full content
            # Note some assistant messages are themselves a list, with one
            #  text message followed by a tool request message
            return {
                "role": role,
                "content": content,
                "message_type": type(message).__name__,
            }

        except Exception as e:
            return {
                "role": "unknown",
                "content": f"<Error extracting message: {e}>",
                "message_type": type(message).__name__,
            }

    def _get_tool_result_preview(self, result) -> str:
        """Get a preview of tool result for logging."""
        try:
            # First check if this is a Strands tool result structure
            if isinstance(result, dict) and "content" in result:
                content_list = result.get("content", [])
                if content_list and isinstance(content_list, list):
                    for content_item in content_list:
                        if isinstance(content_item, dict) and "text" in content_item:
                            import json

                            try:
                                # Try to parse the text as JSON to check for success field
                                parsed_content = json.loads(content_item["text"])
                                if (
                                    isinstance(parsed_content, dict)
                                    and "success" in parsed_content
                                ):
                                    success = parsed_content["success"]
                                    if success:
                                        data_preview = str(
                                            parsed_content.get(
                                                "result_csv_s3_uri",
                                                parsed_content.get("data", ""),
                                            )
                                        )
                                        return f"Success: {data_preview}"
                                    else:
                                        error = parsed_content.get(
                                            "error", "Unknown error"
                                        )
                                        return f"Error: {error}"
                            except (json.JSONDecodeError, TypeError):
                                # If parsing fails, fall through to generic handling
                                pass

            # Fallback to original logic for other result types
            if isinstance(result, dict):
                if "success" in result:
                    success = result["success"]
                    if success:
                        data_preview = str(result.get("data", ""))
                        return f"Success: {data_preview}"
                    else:
                        error = result.get("error", "Unknown error")
                        return f"Error: {error}"
                else:
                    # Generic dict preview
                    return str(result)
            else:
                return str(result)
        except Exception as e:
            return f"<Error getting preview: {e}>"

    def log_execution_summary(self) -> None:
        """Log a summary of the execution statistics."""
        stats = self.execution_stats

        self.monitor_logger.info("📊 Execution Summary:")
        self.monitor_logger.info(f"  • Messages added: {stats['messages_added']}")
        self.monitor_logger.info(f"  • Tool invocations: {stats['tool_invocations']}")
        self.monitor_logger.info(f"  • Model invocations: {stats['model_invocations']}")
        self.monitor_logger.info(
            f"  • Requests processed: {stats['requests_processed']}"
        )

        if stats["start_time"] and stats["end_time"]:
            duration = stats["end_time"] - stats["start_time"]
            self.monitor_logger.info(
                f"  • Total duration: {duration.total_seconds():.2f}s"
            )

        # Log cache metrics summary
        cache_summary = self.cache_metrics.get_summary()
        if cache_summary["requests"] > 0:
            self.monitor_logger.info(
                f"  • Cache hit rate: {cache_summary['cache_hit_rate']}"
            )
            self.monitor_logger.info(
                f"  • Tokens from cache: {cache_summary['tokens_read_from_cache']}"
            )
            self.monitor_logger.info(
                f"  • Tokens cached: {cache_summary['tokens_written_to_cache']}"
            )

    def get_execution_report(self) -> Dict[str, Any]:
        """Get a comprehensive execution report."""
        return {
            "execution_stats": self.execution_stats.copy(),
            "message_history": self.message_history.copy(),
            "tool_history": self.tool_history.copy(),
            "model_history": self.model_history.copy(),
            "cache_metrics": self.cache_metrics.get_summary(),
        }

    def _write_to_log_file(self, data: Dict[str, Any]) -> None:
        """Write data to the log file in pretty-printed JSON format."""
        if not self.log_file_path:
            return

        try:
            # Convert data to pretty-printed JSON
            json_data = self._safe_json_serialize(data)

            # Write to file with proper formatting
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(json_data, indent=2, sort_keys=True))
                f.write("\n")  # Add newline between entries
        except Exception as e:
            self.monitor_logger.error(f"Error writing to log file: {e}")

    def _safe_json_serialize(self, obj: Any) -> Any:
        """Convert object to JSON-serializable format, handling non-serializable types."""
        if isinstance(obj, dict):
            return {k: self._safe_json_serialize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._safe_json_serialize(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Convert non-serializable types to strings
            return str(obj)

    def reset_stats(self) -> None:
        """Reset all execution statistics and history."""
        self.execution_stats = {
            "messages_added": 0,
            "tool_invocations": 0,
            "model_invocations": 0,
            "requests_processed": 0,
            "start_time": None,
            "end_time": None,
        }
        self.message_history.clear()
        self.tool_history.clear()
        self.model_history.clear()

        # Log reset to file
        if self.log_file_path:
            self._write_to_log_file(
                {"event": "stats_reset", "timestamp": datetime.now().isoformat()}
            )
