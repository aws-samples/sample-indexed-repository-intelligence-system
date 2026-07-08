# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Backend Agent Creation Module

This module provides a simple interface to create agents for the WebSocket backend
by reusing the centralized create_agent function from agentic_chat.py.
"""

import logging
from typing import Dict, Any
from iris.agentic_chat import create_agent
from iris.utils.utils import load_default_config, construct_output_dir

log = logging.getLogger(__name__)


def create_backend_agent():
    """
    Create a backend agent by using the centralized create_agent function.

    This function calls the centralized create_agent from agentic_chat.py
    with appropriate parameters for WebSocket backend use.

    Returns:
        Agent: Configured agent instance
    """
    try:
        # Use the centralized create_agent function with WebSocket-specific settings
        agent = create_agent(
            codebase_dir=None,  # Will use default from config
            include_monitoring=True,  # Enable monitoring for WebSocket backend
        )

        log.info("Backend agent created successfully using centralized create_agent")
        return agent

    except Exception as e:
        log.error(f"Failed to create backend agent: {str(e)}")
        raise


def setup_codebase() -> Dict[str, Any]:
    """
    Setup codebase and return configuration info.

    Returns:
        Dict: Configuration information
    """
    try:
        config = load_default_config()
        codebase_dir = config["codebase_dir"]
        output_folder = construct_output_dir(codebase_dir=codebase_dir)

        return {
            "codebase_dir": codebase_dir,
            "output_folder": str(output_folder),
            "status": "ready",
        }

    except Exception as e:
        log.error(f"Failed to setup codebase: {str(e)}")
        return {"status": "error", "error": str(e)}
