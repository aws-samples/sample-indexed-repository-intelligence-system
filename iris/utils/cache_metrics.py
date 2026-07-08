# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Cache metrics tracking for prompt caching performance monitoring."""

import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """Track prompt caching metrics for cost and performance analysis."""

    cache_hits: int = 0
    cache_misses: int = 0
    tokens_read_from_cache: int = 0
    tokens_written_to_cache: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    requests: int = 0
    start_time: datetime = field(default_factory=datetime.now)

    def record_response(self, response: Dict) -> None:
        """Record cache metrics from an Amazon Bedrock response."""
        self.requests += 1

        usage = response.get("usage", {})
        cache_read = usage.get("cacheReadInputTokens", 0)
        cache_write = usage.get("cacheWriteInputTokens", 0)
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)

        if cache_read > 0:
            self.cache_hits += 1
            self.tokens_read_from_cache += cache_read
        elif cache_write == 0:
            self.cache_misses += 1

        if cache_write > 0:
            self.tokens_written_to_cache += cache_write

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

    def get_summary(self) -> Dict:
        """Get summary of cache metrics."""
        return {
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": f"{self.get_cache_hit_rate():.1f}%",
            "tokens_read_from_cache": self.tokens_read_from_cache,
            "tokens_written_to_cache": self.tokens_written_to_cache,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
        }

    def log_summary(self) -> None:
        """Log cache metrics summary."""
        summary = self.get_summary()
        log.info(
            f"Cache Metrics: {summary['cache_hits']}/{summary['requests']} hits ({summary['cache_hit_rate']}), "
            f"{summary['tokens_read_from_cache']} tokens from cache, "
            f"{summary['tokens_written_to_cache']} tokens cached"
        )


# Global cache metrics instance
_global_cache_metrics: Optional[CacheMetrics] = None


def get_cache_metrics() -> CacheMetrics:
    """Get or create global cache metrics instance."""
    global _global_cache_metrics
    if _global_cache_metrics is None:
        _global_cache_metrics = CacheMetrics()
    return _global_cache_metrics


def reset_cache_metrics() -> None:
    """Reset global cache metrics."""
    global _global_cache_metrics
    _global_cache_metrics = CacheMetrics()
