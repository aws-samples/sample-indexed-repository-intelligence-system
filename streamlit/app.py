# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import asyncio
import queue
import threading

import streamlit as st
from pathlib import Path

# Import from new iris package structure
from iris.utils.utils import (
    load_default_config,
    construct_output_dir,
    get_additional_context,
    get_ignore_patterns,
)
from iris.utils.logging_setup import configure_logging
from iris.generate_context import generate_context
from iris.file_system.file_management import validate_tree
from iris.agentic_chat import create_agent

# Set up page config
st.set_page_config(page_title="IRIS Chat", layout="wide")


def get_config_and_paths(custom_codebase_dir=None):
    """Get configuration and calculate paths using new API"""
    try:
        config = load_default_config()

        # Use custom codebase directory if provided, otherwise use config default
        if custom_codebase_dir:
            codebase_dir = Path(custom_codebase_dir)
        else:
            codebase_dir = Path(config["codebase_dir"])

        output_dir = construct_output_dir(codebase_dir=codebase_dir)
        return config, codebase_dir, Path(output_dir)
    except Exception as e:
        st.error(f"Error loading configuration: {str(e)}")
        st.stop()


def ensure_context_ready(codebase_dir, output_dir, config):
    """Ensure codebase context is generated using new API"""
    try:
        # Get additional context and ignore patterns using new utility functions
        additional_context = get_additional_context()
        ignore_patterns = get_ignore_patterns(codebase_dir=codebase_dir)

        context_result = generate_context(
            codebase_dir=str(codebase_dir),
            output_dir=str(output_dir),
            ignore_patterns=ignore_patterns,
            additional_context=additional_context,
            verbose=False,
        )

        return context_result
    except Exception as e:
        st.error(f"Error generating context: {str(e)}")
        return None


def get_or_create_agent(codebase_dir):
    """Get the IRIS Strands agent for this session, creating it once.

    The agent is cached in st.session_state and holds the conversation
    history in-memory (Streamlit reruns the script on every interaction, so
    rebuilding the agent each time would drop that memory). The agent is keyed
    to the codebase so switching codebases builds a fresh one.
    """
    cached_dir = st.session_state.get("agent_codebase")
    if "agent" not in st.session_state or cached_dir != str(codebase_dir):
        st.session_state.agent = create_agent(codebase_dir=str(codebase_dir))
        st.session_state.agent_codebase = str(codebase_dir)
    return st.session_state.agent


def stream_agent_response(agent, prompt):
    """Bridge the agent's async streaming into a sync generator of text chunks.

    Streamlit runs synchronously, so we drive ``agent.stream_async`` on a
    background thread and hand text chunks back through a queue.
    """
    chunks: queue.Queue = queue.Queue()
    _DONE = object()

    def _run():
        async def _consume():
            async for event in agent.stream_async(prompt):
                if "data" in event:
                    chunks.put(event["data"])

        try:
            asyncio.run(_consume())
        except Exception as e:  # surface errors to the consumer
            chunks.put(e)
        finally:
            chunks.put(_DONE)

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()

    while True:
        item = chunks.get()
        if item is _DONE:
            break
        if isinstance(item, Exception):
            raise item
        yield item

    worker.join()


def clear_chat_history():
    """Clear both the displayed history and the agent's in-memory history."""
    try:
        # Reset the agent's conversation memory
        if "agent" in st.session_state:
            st.session_state.agent.messages = []

        # Clear the displayed chat history and add a welcome message
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": "Chat history has been cleared. What would you like to know about the codebase?",
            }
        ]

        st.success("Chat history cleared successfully!")
    except Exception as e:
        st.error(f"Error clearing chat history: {str(e)}")


def display_context_status(context_result):
    """Display context generation status information"""
    if not context_result:
        return

    if context_result.status == "update_complete":
        st.info(f"✅ Context updated: {context_result.message}")
        if context_result.processed_files:
            with st.expander(
                f"📁 Processed {len(context_result.processed_files)} files"
            ):
                for file_path in context_result.processed_files[:10]:  # Show first 10
                    st.text(f"• {file_path}")
                if len(context_result.processed_files) > 10:
                    st.text(
                        f"... and {len(context_result.processed_files) - 10} more files"
                    )

    elif context_result.status == "no_op":
        st.success("✅ Codebase context is up to date")

    elif context_result.status == "error":
        st.error(f"❌ Context generation failed: {context_result.message}")


def display_tree_validation(files_result):
    """Display tree validation information and get user confirmation"""
    if not files_result:
        return False

    st.header("🌳 Codebase Tree Validation")

    # Display change information
    if files_result.has_changed:
        change_details = files_result.change_details

        st.warning(f"📝 Found changes in {len(files_result.files_to_process)} files")

        col1, col2, col3 = st.columns(3)

        with col1:
            if change_details["new_files"]:
                st.info(f"📄 **New files:** {len(change_details['new_files'])}")
                with st.expander("View new files"):
                    for file_path in change_details["new_files"][:10]:
                        st.text(f"+ {file_path}")
                    if len(change_details["new_files"]) > 10:
                        st.text(f"... and {len(change_details['new_files']) - 10} more")

        with col2:
            if change_details["modified_files"]:
                st.info(
                    f"📝 **Modified files:** {len(change_details['modified_files'])}"
                )
                with st.expander("View modified files"):
                    for file_path in change_details["modified_files"][:10]:
                        st.text(f"~ {file_path}")
                    if len(change_details["modified_files"]) > 10:
                        st.text(
                            f"... and {len(change_details['modified_files']) - 10} more"
                        )

        with col3:
            if change_details["deleted_files"]:
                st.info(f"🗑️ **Deleted files:** {len(change_details['deleted_files'])}")
                with st.expander("View deleted files"):
                    for file_path in change_details["deleted_files"][:10]:
                        st.text(f"- {file_path}")
                    if len(change_details["deleted_files"]) > 10:
                        st.text(
                            f"... and {len(change_details['deleted_files']) - 10} more"
                        )
    else:
        st.success("✅ No changes detected - codebase context is up to date")

    # Display file tree
    st.subheader(f"📁 File Tree ({files_result.total_files} files)")

    # Show tree in expandable section to save space
    with st.expander("View complete file tree", expanded=False):
        st.text(files_result.tree_display)

    # Show summary
    st.info(f"**Total files to analyze:** {files_result.total_files}")

    # Get user confirmation
    st.subheader("⚠️ Confirmation Required")

    if files_result.has_changed and files_result.files_to_process:
        st.warning(
            f"**This will process {len(files_result.files_to_process)} files** and may take several minutes "
            f"and incur AWS costs for LLM usage."
        )

    confirmation_text = "Does the tree above capture all the files and only the files you want to include in the analysis?"
    st.write(confirmation_text)

    col1, col2, col3 = st.columns([2, 1, 1])

    with col2:
        if st.button("✅ Yes, Proceed", type="primary", use_container_width=True):
            return True

    with col3:
        if st.button("❌ No, Cancel", use_container_width=True):
            st.error(
                "❌ Analysis cancelled. Please adjust your ignore patterns in the config file and refresh the page."
            )
            st.stop()

    return False


def main():
    st.title("IRIS Chat")

    # Sidebar for codebase configuration
    st.sidebar.header("Configuration")

    # Load default config to get the default codebase directory
    try:
        default_config = load_default_config()
        default_codebase = default_config["codebase_dir"]
    except Exception:
        default_codebase = ""

    # Codebase directory input
    custom_codebase = st.sidebar.text_input(
        "Codebase Directory",
        value=default_codebase,
        help="Path to the codebase you want to analyze. Leave as default or specify a new path.",
        placeholder="/path/to/your/codebase",
    )

    # Validate the codebase directory
    if custom_codebase and not Path(custom_codebase).exists():
        st.sidebar.error(f"❌ Directory does not exist: {custom_codebase}")
        st.stop()

    # Get configuration and paths with custom codebase if provided
    config, codebase_dir, output_dir = get_config_and_paths(
        custom_codebase_dir=custom_codebase if custom_codebase else None
    )

    # Display codebase information
    st.sidebar.header("Codebase Information")
    st.sidebar.text(f"📂 Codebase: {codebase_dir}")
    st.sidebar.text(f"💾 Output: {output_dir}")

    # Reset states if codebase directory changed
    if "current_codebase" not in st.session_state:
        st.session_state.current_codebase = str(codebase_dir)
    elif st.session_state.current_codebase != str(codebase_dir):
        # Codebase changed, reset all states
        st.session_state.current_codebase = str(codebase_dir)
        for key in ["tree_validated", "context_ready", "files_result", "chat_history"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # Configure logging (only once)
    if "logging_configured" not in st.session_state:
        try:
            configure_logging(output_dir)
            st.session_state.logging_configured = True
        except Exception as e:
            st.warning(f"Logging configuration warning: {str(e)}")

    # Tree validation and context preparation
    if "tree_validated" not in st.session_state:
        # Step 1: Validate tree and get user confirmation
        st.info("🔍 **Step 1:** Validating codebase tree...")

        try:
            files_result = validate_tree(codebase_dir=str(codebase_dir))

            # Show tree validation UI and wait for user confirmation
            if display_tree_validation(files_result):
                st.session_state.tree_validated = True
                st.session_state.files_result = files_result
                st.rerun()
            else:
                # User hasn't confirmed yet, stop here
                st.stop()
        except Exception as e:
            st.error(f"Error validating tree: {str(e)}")
            st.stop()

    # Step 2: Generate context after validation
    if "context_ready" not in st.session_state and st.session_state.get(
        "tree_validated", False
    ):
        st.info("🔄 **Step 2:** Generating codebase context...")

        files_result = st.session_state.files_result

        # Show what will be processed
        if files_result.has_changed and files_result.files_to_process:
            st.warning(f"Processing {len(files_result.files_to_process)} files...")

        with st.spinner("🤖 Analyzing codebase... This may take several minutes."):
            context_result = ensure_context_ready(codebase_dir, output_dir, config)
            if context_result:
                display_context_status(context_result)
                st.session_state.context_ready = True
                st.success("✅ Codebase analysis complete! You can now start chatting.")
                st.rerun()
            else:
                st.error("Failed to prepare codebase context")
                st.stop()

    # Only show chat interface after context is ready
    if not st.session_state.get("context_ready", False):
        st.info(
            "Please complete the tree validation and context generation steps above."
        )
        st.stop()

    # Create (or retrieve) the agent that holds this session's conversation.
    agent = get_or_create_agent(codebase_dir)

    # Session state initialization. Chat history mirrors the agent's memory for
    # display purposes; the agent itself is the source of truth for context.
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": f"What would you like to know about the codebase at {codebase_dir}?",
            }
        ]

    # Clear chat history button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("🗑️ Clear Chat History"):
            clear_chat_history()
            st.rerun()

    with col2:
        if st.button("🔄 Refresh Context"):
            # Reset validation states to restart the process. Also drop the
            # cached agent and the displayed transcript so the rebuilt agent's
            # (empty) memory and the shown chat history stay in sync.
            for key in [
                "tree_validated",
                "context_ready",
                "files_result",
                "agent",
                "agent_codebase",
                "chat_history",
            ]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Chat input
    user_input = st.chat_input("Ask something about the codebase...")

    if user_input:
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        # Display user message
        with st.chat_message("user"):
            st.write(user_input)

        # Generate AI response by streaming from the agent
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""
            try:
                with st.spinner("🤖 Thinking..."):
                    for chunk in stream_agent_response(agent, user_input):
                        if chunk:  # Only process non-empty chunks
                            full_response += chunk
                            response_placeholder.write(full_response)
            except Exception as e:
                error_msg = f"Error processing response stream: {str(e)}"
                st.error(error_msg)
                full_response = error_msg

        # Add AI response to displayed chat history (the agent already retains
        # the full conversation in its own memory).
        st.session_state.chat_history.append(
            {"role": "assistant", "content": full_response}
        )


if __name__ == "__main__":
    main()
