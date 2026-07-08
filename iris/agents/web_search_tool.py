# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import logging
from ddgs import DDGS
from strands import tool

log = logging.getLogger(__name__)


@tool
def web_search(query: str, max_results: int = 10) -> str:
    """
    Search the web using DuckDuckGo.

    Args:
        query: The search query
        max_results: Maximum number of results to return

    Returns:
        A list of search results. Each result contains a web page title, page URL and a snippet of relevant page content
    """

    try:
        return DDGS().text(query, max_results=max_results, backend="duckduckgo")
    except Exception as e:
        log.error(f"Web search failed: {e}")
        return f"Web search failed: {str(e)}"
