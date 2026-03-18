"""SyncEventBus — event queue with retry logic and dead letter queue.

Every data movement between the platform and external systems flows through
the event bus as a SyncEvent. The bus handles:
    - Event creation and queuing
    - Processing with retry (exponential backoff)
    - Dead letter queue for exhausted retries
    - Idempotency (duplicate detection)
    - Audit logging

Architecture:
    Producer (webhook/push) → SyncEventBus.publish() → Queue → process() → Consumer
                                                          ↓ (on failure)
                                                     Retry queue → DLQ
"""
import hashlib
import logging
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.connector import ConnectorType as _CT

from app.core.mongodb import get_database
from app.models.connector import (
    SyncEvent,
    SyncEventType,
    SyncEventStatus,
    SyncDirection,
    ConnectorType,
)

logger = logging.getLogger(__name__)

# Type alias for event handler callbacks
EventHandler = Callable[[SyncEvent], Awaitable[bool]]


class SyncEventBus:
    """In-memory event bus for sync operations.

    In production, this would be backed by Redis Streams, RabbitMQ, or
    a MongoDB-based queue. The in-memory implementation provides the same
    interface for development and demo.
    """

    # Retry schedule: exponential backoff in seconds
    RETRY_DELAYS = [10, 30, 60, 300, 900]  # 10s, 30s, 1m, 5m, 15m

    def __init__(self):
        # Pending events: ready to process
        self._pending: deque[SyncEvent] = deque()
        # All events by ID: event_id -> SyncEvent (audit trail)
        self._events: Dict[str, SyncEvent] = {}
        # Idempotency: idempotency_key -> event_id (dedupe)
        self._idempotency_index: Dict[str, str] = {}
        # Dead letter queue: events that exhausted retries
        self._dead_letter: List[SyncEvent] = []
        # Registered handlers: event_type -> handler function
        self._handlers: Dict[SyncEventType, EventHandler] = {}
        # Stats
        self._stats = {
            "total_published": 0,
            "total_processed": 0,
            "total_failed": 0,
            "total_dead_letter": 0,
            "total_duplicates_skipped": 0,
        }
        # SLO metric accumulators: (tenant_id, connector_type) -> list of latency_ms
        self._slo_accumulators: Dict[str, List[float]] = {}

    def _events_col(self):
        db = get_database()
        return db.sync_events if db is not None else None

    async def hydrate_from_db(self) -> None:
        """Hydrate in-memory queues from MongoDB event store."""
        col = self._events_col()
        if col is None:
            return

        self._pending.clear()
        self._events.clear()
        self._dead_letter.clear()
        self._idempotency_index.clear()

        async for doc in col.find({}, {"_id": 0}):
            try:
                event = SyncEvent(**doc)
            except Exception:
                logger.exception("Failed to parse sync event during hydration: %s", doc.get("event_id"))
                continue
            self._events[event.event_id] = event
            self._idempotency_index[event.idempotency_key] = event.event_id

            if event.status in (SyncEventStatus.PENDING, SyncEventStatus.FAILED):
                self._pending.append(event)
            elif event.status == SyncEventStatus.DEAD_LETTER:
                self._dead_letter.append(event)

        logger.info(
            "Sync events hydrated: total=%d pending=%d dead_letter=%d",
            len(self._events),
            len(self._pending),
            len(self._dead_letter),
        )

    async def _persist_event(self, event: SyncEvent) -> None:
        col = self._events_col()
        if col is None:
            return
        await col.update_one(
            {"event_id": event.event_id},
            {"$set": event.model_dump()},
            upsert=True,
        )

    # ── Event Publishing ─────────────────────────────────────────────────

    def generate_idempotency_key(
        self,
        source: str,
        external_id: str,
        event_type: str,
        timestamp: str,
    ) -> str:
        """Generate a deterministic idempotency key for deduplication.

        Same source + external_id + event_type + timestamp = same key.
        """
        raw = f"{source}:{external_id}:{event_type}:{timestamp}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    async def publish(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        event_type: SyncEventType,
        direction: SyncDirection,
        source: str,
        payload: Dict[str, Any],
        incident_id: Optional[str] = None,
        external_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Optional[SyncEvent]:
        """Publish a new sync event to the bus.

        Args:
            tenant_id: Tenant this event belongs to.
            connector_type: Which connector system.
            event_type: What happened (ticket_created, status_changed, etc.).
            direction: Inbound or outbound.
            source: Origin ("webhook", "api_push", "manual_sync").
            payload: The data being synced.
            incident_id: Internal incident ID (if known).
            external_id: External ticket ID (if known).
            idempotency_key: Optional custom key. Auto-generated if not provided.

        Returns:
            The created SyncEvent, or None if duplicate (idempotent skip).
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = self.generate_idempotency_key(
                source=source,
                external_id=external_id or incident_id or "",
                event_type=event_type.value,
                timestamp=datetime.utcnow().isoformat()[:16],  # Minute-level granularity
            )

        # Deduplicate
        if idempotency_key in self._idempotency_index:
            existing_id = self._idempotency_index[idempotency_key]
            self._stats["total_duplicates_skipped"] += 1
            logger.info(
                f"Duplicate event skipped: key={idempotency_key} "
                f"existing_event={existing_id}"
            )
            return None

        # Create event
        event = SyncEvent(
            event_id=f"EVT_{uuid.uuid4().hex[:12].upper()}",
            tenant_id=tenant_id,
            connector_type=connector_type,
            incident_id=incident_id,
            external_id=external_id,
            event_type=event_type,
            direction=direction,
            source=source,
            payload=payload,
            status=SyncEventStatus.PENDING,
            retry_count=0,
            max_retries=len(self.RETRY_DELAYS),
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow(),
        )

        # Store
        self._events[event.event_id] = event
        self._idempotency_index[idempotency_key] = event.event_id
        self._pending.append(event)
        self._stats["total_published"] += 1
        await self._persist_event(event)

        logger.info(
            f"Published sync event: {event.event_id} "
            f"type={event_type.value} dir={direction.value} "
            f"tenant={tenant_id} source={source}"
        )
        return event

    # ── Event Processing ─────────────────────────────────────────────────

    def register_handler(
        self, event_type: SyncEventType, handler: EventHandler
    ) -> None:
        """Register a handler function for a specific event type.

        The handler receives a SyncEvent and returns True on success,
        False on failure (will be retried).
        """
        self._handlers[event_type] = handler
        logger.info(f"Registered handler for {event_type.value}: {handler.__name__}")

    async def process_next(self) -> Optional[SyncEvent]:
        """Process the next pending event in the queue.

        Returns:
            The processed event, or None if queue is empty.
        """
        if not self._pending:
            return None

        event = self._pending.popleft()

        # Check if it's scheduled for later retry
        if event.next_retry_at and datetime.utcnow() < event.next_retry_at:
            # Not ready yet, put back
            self._pending.append(event)
            return None

        handler = self._handlers.get(event.event_type)
        if not handler:
            logger.warning(
                f"No handler for event type {event.event_type.value}, "
                f"sending to DLQ: {event.event_id}"
            )
            await self._move_to_dead_letter(event, "No handler registered")
            return event

        # Process
        event.status = SyncEventStatus.PROCESSING
        try:
            success = await handler(event)

            if success:
                event.status = SyncEventStatus.COMPLETED
                event.processed_at = datetime.utcnow()
                self._stats["total_processed"] += 1
                await self._persist_event(event)

                # Record latency for SLO metrics
                latency_ms = (event.processed_at - event.created_at).total_seconds() * 1000
                acc_key = f"{event.tenant_id}:{event.connector_type.value}"
                self._slo_accumulators.setdefault(acc_key, []).append(latency_ms)

                logger.info(f"Event processed successfully: {event.event_id}")
            else:
                await self._handle_failure(event, "Handler returned False")

        except Exception as e:
            await self._handle_failure(event, str(e))

        return event

    async def process_all_pending(self) -> Dict[str, int]:
        """Process all pending events. Returns counts by status."""
        counts = {"processed": 0, "failed": 0, "retrying": 0, "dead_letter": 0}

        # Snapshot current pending to avoid infinite loop on re-queued items
        batch_size = len(self._pending)
        for _ in range(batch_size):
            event = await self.process_next()
            if not event:
                break
            if event.status == SyncEventStatus.COMPLETED:
                counts["processed"] += 1
            elif event.status == SyncEventStatus.FAILED:
                counts["retrying"] += 1
            elif event.status == SyncEventStatus.DEAD_LETTER:
                counts["dead_letter"] += 1

        return counts

    async def _handle_failure(self, event: SyncEvent, error_message: str) -> None:
        """Handle a failed event: retry or move to DLQ."""
        event.retry_count += 1
        event.error_message = error_message
        self._stats["total_failed"] += 1

        if event.retry_count >= event.max_retries:
            await self._move_to_dead_letter(event, error_message)
        else:
            # Schedule retry with exponential backoff
            delay_index = min(event.retry_count - 1, len(self.RETRY_DELAYS) - 1)
            delay_seconds = self.RETRY_DELAYS[delay_index]
            event.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
            event.status = SyncEventStatus.FAILED

            # Re-queue
            self._pending.append(event)
            await self._persist_event(event)
            logger.warning(
                f"Event failed (attempt {event.retry_count}/{event.max_retries}), "
                f"retry in {delay_seconds}s: {event.event_id} — {error_message}"
            )

    async def _move_to_dead_letter(self, event: SyncEvent, reason: str) -> None:
        """Move an exhausted event to the dead letter queue."""
        event.status = SyncEventStatus.DEAD_LETTER
        event.error_message = reason
        event.processed_at = datetime.utcnow()
        self._dead_letter.append(event)
        self._stats["total_dead_letter"] += 1
        await self._persist_event(event)
        logger.error(
            f"Event moved to DLQ: {event.event_id} — {reason} "
            f"(after {event.retry_count} retries)"
        )

    # ── Dead Letter Queue ────────────────────────────────────────────────

    def get_dead_letter_events(
        self, tenant_id: Optional[str] = None, limit: int = 50
    ) -> List[SyncEvent]:
        """Get events from the dead letter queue."""
        events = self._dead_letter
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        return events[:limit]

    async def replay_dead_letter(self, event_id: str) -> Optional[SyncEvent]:
        """Replay a dead letter event — reset and re-queue for processing.

        Args:
            event_id: The event to replay.

        Returns:
            The re-queued event, or None if not found in DLQ.
        """
        event = None
        for i, e in enumerate(self._dead_letter):
            if e.event_id == event_id:
                event = self._dead_letter.pop(i)
                break

        if not event:
            return None

        # Reset for reprocessing
        event.status = SyncEventStatus.PENDING
        event.retry_count = 0
        event.error_message = None
        event.next_retry_at = None
        event.processed_at = None

        self._pending.append(event)
        await self._persist_event(event)
        logger.info(f"Replayed DLQ event: {event.event_id}")
        return event

    async def replay_all_dead_letter(self, tenant_id: str) -> int:
        """Replay all DLQ events for a tenant. Returns count replayed."""
        to_replay = [e for e in self._dead_letter if e.tenant_id == tenant_id]
        count = 0
        for event in to_replay:
            result = await self.replay_dead_letter(event.event_id)
            if result:
                count += 1
        return count

    # ── Cleanup ────────────────────────────────────────────────────────

    async def clear_tenant_events(self, tenant_id: str) -> int:
        """Remove all sync events for a tenant. Returns count of removed events."""
        to_remove = [eid for eid, e in self._events.items() if e.tenant_id == tenant_id]
        for eid in to_remove:
            event = self._events.pop(eid, None)
            if event:
                ikey = event.idempotency_key
                self._idempotency_index.pop(ikey, None)
                try:
                    self._pending.remove(event)
                except ValueError:
                    pass
        self._dead_letter = [e for e in self._dead_letter if e.tenant_id != tenant_id]
        # Remove from DB
        col = self._events_col()
        if col is not None:
            await col.delete_many({"tenant_id": tenant_id})
        logger.info("Cleared %d sync events for tenant %s", len(to_remove), tenant_id)
        return len(to_remove)

    # ── Query & Audit ────────────────────────────────────────────────────

    def get_event(self, event_id: str) -> Optional[SyncEvent]:
        """Get a specific event by ID."""
        return self._events.get(event_id)

    def get_events(
        self,
        tenant_id: Optional[str] = None,
        connector_type: Optional[ConnectorType] = None,
        status: Optional[SyncEventStatus] = None,
        direction: Optional[SyncDirection] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[SyncEvent]:
        """Query events with filters (audit log)."""
        events = list(self._events.values())

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if connector_type:
            events = [e for e in events if e.connector_type == connector_type]
        if status:
            events = [e for e in events if e.status == status]
        if direction:
            events = [e for e in events if e.direction == direction]

        # Sort by created_at descending
        events.sort(key=lambda e: e.created_at, reverse=True)
        total = len(events)
        return events[offset : offset + limit], total

    def get_sync_status(self, tenant_id: str) -> Dict[str, Any]:
        """Get sync status summary for a tenant."""
        tenant_events = [e for e in self._events.values() if e.tenant_id == tenant_id]
        pending = sum(1 for e in tenant_events if e.status == SyncEventStatus.PENDING)
        processing = sum(1 for e in tenant_events if e.status == SyncEventStatus.PROCESSING)
        completed = sum(1 for e in tenant_events if e.status == SyncEventStatus.COMPLETED)
        failed = sum(1 for e in tenant_events if e.status == SyncEventStatus.FAILED)
        dead_letter = sum(1 for e in tenant_events if e.status == SyncEventStatus.DEAD_LETTER)

        last_event = max(tenant_events, key=lambda e: e.created_at) if tenant_events else None

        return {
            "tenant_id": tenant_id,
            "total_events": len(tenant_events),
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "dead_letter": dead_letter,
            "last_event_at": last_event.created_at.isoformat() if last_event else None,
            "last_event_type": last_event.event_type.value if last_event else None,
            "queue_depth": len(self._pending),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get global bus statistics."""
        return {
            **self._stats,
            "queue_depth": len(self._pending),
            "dlq_depth": len(self._dead_letter),
            "total_events_stored": len(self._events),
            "handlers_registered": list(h.value for h in self._handlers.keys()),
        }

    # ── SLO Metrics ───────────────────────────────────────────────────────

    def get_slo_summary(self, tenant_id: str, connector_type: Optional[ConnectorType] = None) -> Dict[str, Any]:
        """Get real-time SLO summary from in-memory accumulators."""
        import statistics

        results = {}
        for acc_key, latencies in self._slo_accumulators.items():
            t_id, ct = acc_key.split(":", 1)
            if t_id != tenant_id:
                continue
            if connector_type and ct != connector_type.value:
                continue

            sorted_lat = sorted(latencies)
            n = len(sorted_lat)
            results[ct] = {
                "connector_type": ct,
                "sample_count": n,
                "latency_avg": statistics.mean(sorted_lat) if n else 0,
                "latency_p50": sorted_lat[int(n * 0.5)] if n else 0,
                "latency_p90": sorted_lat[int(n * 0.9)] if n else 0,
                "latency_p99": sorted_lat[int(n * 0.99)] if n else 0,
                "success_rate": self._compute_success_rate(tenant_id, ct),
            }
        return results

    def _compute_success_rate(self, tenant_id: str, connector_type_value: str) -> float:
        """Compute success rate for a tenant+connector from in-memory events."""
        tenant_events = [
            e for e in self._events.values()
            if e.tenant_id == tenant_id and e.connector_type.value == connector_type_value
        ]
        if not tenant_events:
            return 1.0
        completed = sum(1 for e in tenant_events if e.status == SyncEventStatus.COMPLETED)
        return completed / len(tenant_events)

    async def get_slo_metrics(
        self,
        tenant_id: str,
        connector_type: Optional[str] = None,
        period_type: str = "hourly",
        limit: int = 24,
    ) -> List[Dict[str, Any]]:
        """Query historical SLO metrics from MongoDB."""
        col = self._slo_metrics_col()
        if col is None:
            return []

        query: Dict[str, Any] = {"tenant_id": tenant_id, "period_type": period_type}
        if connector_type:
            query["connector_type"] = connector_type

        metrics = []
        async for doc in col.find(query, {"_id": 0}).sort("period_start", -1).limit(limit):
            metrics.append(doc)
        return metrics

    async def flush_slo_metrics(self) -> int:
        """Compute SLO percentiles from accumulators and persist to MongoDB.

        Call periodically (e.g. every hour). Returns number of metric records flushed.
        """
        import statistics

        col = self._slo_metrics_col()
        if col is None:
            return 0

        now = datetime.utcnow()
        # Round to hour boundary
        period_end = now.replace(minute=0, second=0, microsecond=0)
        period_start = period_end - timedelta(hours=1)
        count = 0

        for acc_key, latencies in list(self._slo_accumulators.items()):
            if not latencies:
                continue

            tenant_id, ct = acc_key.split(":", 1)
            sorted_lat = sorted(latencies)
            n = len(sorted_lat)

            # Count events in this period
            tenant_events = [
                e for e in self._events.values()
                if e.tenant_id == tenant_id and e.connector_type.value == ct
                and e.created_at >= period_start and e.created_at < period_end
            ]
            total = len(tenant_events)
            successful = sum(1 for e in tenant_events if e.status == SyncEventStatus.COMPLETED)
            failed = sum(1 for e in tenant_events if e.status in (SyncEventStatus.FAILED, SyncEventStatus.DEAD_LETTER))
            dlq = sum(1 for e in tenant_events if e.status == SyncEventStatus.DEAD_LETTER)

            metric = {
                "metric_id": f"SLO_{uuid.uuid4().hex[:12].upper()}",
                "tenant_id": tenant_id,
                "connector_type": ct,
                "period_start": period_start,
                "period_end": period_end,
                "period_type": "hourly",
                "latency_p50": sorted_lat[int(n * 0.5)] if n else None,
                "latency_p90": sorted_lat[int(n * 0.9)] if n else None,
                "latency_p99": sorted_lat[int(n * 0.99)] if n else None,
                "latency_avg": statistics.mean(sorted_lat) if n else None,
                "total_events": total,
                "successful_events": successful,
                "failed_events": failed,
                "dead_letter_events": dlq,
                "success_rate": successful / total if total else None,
                "created_at": now,
            }

            await col.insert_one(metric)
            count += 1

            # Clear accumulator after flush
            self._slo_accumulators[acc_key] = []

        logger.info("Flushed %d SLO metric records", count)
        return count

    def _slo_metrics_col(self):
        db = get_database()
        return db.slo_metrics if db is not None else None
