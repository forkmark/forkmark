"""Redis Streams message bus — decouples scoring from the API hot path.

Instead of calling Celery tasks directly from the API, the API publishes
"comparison_created" events to a Redis Stream. Evaluation workers consume
from the stream via a consumer group, providing:

    - At-least-once delivery (ack required)
    - Automatic re-delivery of failed messages (pending entries list)
    - Multi-worker consumption without duplication
    - Backpressure visibility (stream length = queue depth)
    - Message ordering within a workspace

Architecture:
    API (producer) → Redis Stream "forkmark:scoring" → Consumer Group "eval-workers"
                                                        ├── worker-1
                                                        ├── worker-2
                                                        └── worker-3

Fallback: when Redis is unavailable, falls back to direct Celery task dispatch.

Usage:
    # Producer (in API endpoint after comparison is created)
    bus = get_message_bus(redis_url)
    bus.publish_scoring_event(comp_id, branch_a_id, branch_b_id, configs, workspace_id)

    # Consumer (in worker process)
    async for event in bus.consume_scoring_events("worker-1"):
        await score_comparison(event)
        bus.ack_event(event["msg_id"])
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Optional, Any

logger = logging.getLogger("forkmark.bus")

STREAM_SCORING = "forkmark:scoring"
CONSUMER_GROUP = "eval-workers"


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

@dataclass
class ScoringEvent:
    """Event published when a comparison needs scoring."""
    msg_id: str                      # Redis message ID (for acking)
    comp_id: str
    branch_a_id: str
    branch_b_id: str
    workspace_id: str
    evaluator_configs: List[Dict]
    published_at: float
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "comp_id": self.comp_id,
            "branch_a_id": self.branch_a_id,
            "branch_b_id": self.branch_b_id,
            "workspace_id": self.workspace_id,
            "evaluator_configs": json.dumps(self.evaluator_configs),
            "published_at": str(self.published_at),
            "retry_count": str(self.retry_count),
        }

    @classmethod
    def from_stream(cls, msg_id: str, data: dict) -> "ScoringEvent":
        return cls(
            msg_id=msg_id,
            comp_id=data.get("comp_id", ""),
            branch_a_id=data.get("branch_a_id", ""),
            branch_b_id=data.get("branch_b_id", ""),
            workspace_id=data.get("workspace_id", "default"),
            evaluator_configs=json.loads(data.get("evaluator_configs", "[]")),
            published_at=float(data.get("published_at", "0")),
            retry_count=int(data.get("retry_count", "0")),
        )


# ---------------------------------------------------------------------------
# Redis Streams Message Bus
# ---------------------------------------------------------------------------

class RedisMessageBus:
    """Redis Streams-backed message bus for scoring events."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            self._redis.ping()
            self._ensure_consumer_group()
            logger.info("Redis message bus connected: %s", self._redis_url)
        except Exception as e:
            logger.warning("Redis message bus failed: %s", e)
            self._redis = None

    def _ensure_consumer_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            self._redis.xgroup_create(STREAM_SCORING, CONSUMER_GROUP, id="0", mkstream=True)
        except Exception as e:
            # Group already exists — that's fine
            if "BUSYGROUP" not in str(e):
                logger.warning("Failed to create consumer group: %s", e)

    @property
    def connected(self) -> bool:
        return self._redis is not None

    def publish_scoring_event(
        self,
        comp_id: str,
        branch_a_id: str,
        branch_b_id: str,
        evaluator_configs: List[Dict],
        workspace_id: str = "default",
    ) -> Optional[str]:
        """Publish a scoring event to the stream.

        Returns the Redis message ID, or None on failure.
        """
        if not self._redis:
            return None

        event = ScoringEvent(
            msg_id="",
            comp_id=comp_id,
            branch_a_id=branch_a_id,
            branch_b_id=branch_b_id,
            workspace_id=workspace_id,
            evaluator_configs=evaluator_configs,
            published_at=time.time(),
        )

        try:
            msg_id = self._redis.xadd(
                STREAM_SCORING,
                event.to_dict(),
                maxlen=100000,  # cap stream at 100k messages (prevent unbounded growth)
            )
            logger.debug("Published scoring event %s for comparison %s", msg_id, comp_id)
            return msg_id
        except Exception as e:
            logger.error("Failed to publish scoring event: %s", e)
            return None

    def consume_scoring_events(
        self,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> List[ScoringEvent]:
        """Consume events from the stream (blocking).

        Args:
            consumer_name: Unique name for this consumer (e.g., "worker-1")
            count: Max events to read per call
            block_ms: Block timeout in milliseconds

        Returns:
            List of ScoringEvent objects. Call ack_event() after processing.
        """
        if not self._redis:
            return []

        try:
            results = self._redis.xreadgroup(
                CONSUMER_GROUP,
                consumer_name,
                {STREAM_SCORING: ">"},
                count=count,
                block=block_ms,
            )

            events = []
            if results:
                for stream_name, messages in results:
                    for msg_id, data in messages:
                        events.append(ScoringEvent.from_stream(msg_id, data))

            return events
        except Exception as e:
            logger.error("Failed to consume events: %s", e)
            return []

    def ack_event(self, msg_id: str) -> bool:
        """Acknowledge a processed event (removes from pending entries list)."""
        if not self._redis:
            return False
        try:
            self._redis.xack(STREAM_SCORING, CONSUMER_GROUP, msg_id)
            return True
        except Exception as e:
            logger.error("Failed to ack event %s: %s", msg_id, e)
            return False

    def claim_stale_events(
        self,
        consumer_name: str,
        min_idle_ms: int = 60000,
        count: int = 10,
    ) -> List[ScoringEvent]:
        """Claim events that have been pending too long (crashed worker recovery).

        This implements the "dead letter" pattern: if a worker crashes before
        acking, another worker picks up the abandoned message.
        """
        if not self._redis:
            return []

        try:
            # XAUTOCLAIM: claim idle messages automatically
            result = self._redis.xautoclaim(
                STREAM_SCORING,
                CONSUMER_GROUP,
                consumer_name,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=count,
            )
            # result format: [new_start_id, [(msg_id, data), ...], [deleted_ids]]
            if result and len(result) >= 2:
                messages = result[1]
                return [ScoringEvent.from_stream(msg_id, data) for msg_id, data in messages]
        except Exception as e:
            # XAUTOCLAIM requires Redis 6.2+
            logger.debug("xautoclaim failed (Redis version?): %s", e)

        return []

    def stream_length(self) -> int:
        """Get the number of messages in the scoring stream."""
        if not self._redis:
            return 0
        try:
            return self._redis.xlen(STREAM_SCORING)
        except Exception:
            return 0

    def pending_count(self) -> int:
        """Get the number of unacknowledged (in-flight) messages."""
        if not self._redis:
            return 0
        try:
            info = self._redis.xpending(STREAM_SCORING, CONSUMER_GROUP)
            return info.get("pending", 0) if isinstance(info, dict) else 0
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Fallback: direct dispatch (no Redis)
# ---------------------------------------------------------------------------

class DirectDispatchBus:
    """Fallback when Redis is unavailable — dispatches directly to Celery."""

    @property
    def connected(self) -> bool:
        return False

    def publish_scoring_event(
        self,
        comp_id: str,
        branch_a_id: str,
        branch_b_id: str,
        evaluator_configs: List[Dict],
        workspace_id: str = "default",
    ) -> Optional[str]:
        """Fall back to direct Celery task dispatch."""
        try:
            from core.celery_app import run_scoring_task
            run_scoring_task.delay(comp_id, branch_a_id, branch_b_id, evaluator_configs)
            logger.debug("Direct-dispatched scoring for %s via Celery", comp_id)
            return f"celery:{comp_id}"
        except Exception as e:
            logger.error("Direct dispatch failed: %s", e)
            return None

    def consume_scoring_events(self, *args, **kwargs):
        return []

    def ack_event(self, msg_id: str) -> bool:
        return True

    def claim_stale_events(self, *args, **kwargs):
        return []

    def stream_length(self) -> int:
        return 0

    def pending_count(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_bus_instance: Optional[RedisMessageBus | DirectDispatchBus] = None


def get_message_bus(redis_url: Optional[str] = None) -> RedisMessageBus | DirectDispatchBus:
    """Get or create the singleton message bus.

    Uses Redis Streams if redis_url is available, otherwise falls back to
    direct Celery dispatch.
    """
    global _bus_instance
    if _bus_instance is not None:
        return _bus_instance

    if redis_url:
        bus = RedisMessageBus(redis_url)
        if bus.connected:
            _bus_instance = bus
            return _bus_instance

    _bus_instance = DirectDispatchBus()
    logger.info("Using direct dispatch (no Redis Streams)")
    return _bus_instance
