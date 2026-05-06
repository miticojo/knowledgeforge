"""Knowledge Catalog (Dataplex) reverse importer for the KnowledgeForge graph.

Milestone C: opt-in projection of Google Knowledge Catalog Entries (BigQuery
tables, Spanner databases, Cloud SQL tables, ...) into the KF Spanner graph as
ArchiMate `DataObject` nodes. Roundtrips with Milestone B (`kc_exporter.py`):

    Milestone B (KF -> KC, outbound): exporter projects DataObjects/edges to KC.
    Milestone C (KC -> KF, inbound):  importer pulls KC Entries into KF graph.

Modes:
    - `import_entry(entry_name)`         -> single-shot fetch + write.
    - `import_batch([entry_name, ...])`  -> N x single-shot.
    - `subscribe(subscription, max=N)`   -> one-pass Pub/Sub pull (ack on
                                            success, nack on failure).
    - `subscribe_streaming(subscription)`-> long-running daemon mode.

Mapping (KC -> KF):
    KC Entry (whitelisted entry_type)  -> ArchiMate `DataObject`
    Aspect "kf-imported-from-kc"       -> persisted as JSON in node `details`
    Embedding                          -> compute_entity_embeddings([...])
    Confidence                         -> EXTRACTED (KC is authoritative)
    source_doc_id                      -> f"kc:{entry_name}"

Idempotency:
    entity_id = uuid.uuid5(NAMESPACE_DNS, entry_name)
    -> stable across runs; the graph_writer upserts in place.

Gating:
    Disabled by default. Set KC_IMPORT_ENABLED=true to opt in. All public
    methods raise `KCImportDisabled` when the flag is off, mirroring
    `KCExportDisabled` in the exporter.

CLI:
    # one-shot batch
    python -m services.kc_importer --once \\
        --entries projects/.../entryGroups/.../entries/foo

    # streaming daemon
    python -m services.kc_importer \\
        --subscription projects/foo/subscriptions/kc-changes
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Whitelist of KC entry types that map cleanly onto an ArchiMate DataObject.
# Extend this set when onboarding a new asset family — anything not listed here
# is silently skipped (the importer logs the skip and the message is acked).
KC_ENTRY_TYPE_WHITELIST: set[str] = {
    "bigquery-table",
    "bigquery-dataset",
    "cloud-bigtable-table",
    "spanner-table",
    "spanner-database",
    "cloud-sql-postgres-table",
    "cloud-sql-postgres-database",
    "alloydb-postgres-table",
    "alloydb-postgres-database",
}

ASPECT_KF_IMPORTED = "kf-imported-from-kc"
SOURCE_SYSTEM = "google-knowledge-catalog"


class KCImportDisabled(RuntimeError):
    """Raised when a KCImporter public method is called with the flag off."""


def _is_enabled() -> bool:
    return os.getenv("KC_IMPORT_ENABLED", "false").lower() in ("1", "true", "yes")


def make_entity_id(entry_name: str) -> str:
    """Deterministic UUID v5 for a KC entry — stable across runs => upserts."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, entry_name))


def _extract_entry_type_short(entry_type: str | None) -> str:
    """Return the trailing segment of an entry_type resource name.

    Dataplex entry_type values look like
    `projects/p/locations/l/entryTypes/bigquery-table`. The whitelist is keyed
    on the short name only.
    """
    if not entry_type:
        return ""
    return entry_type.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


class KCImporter:
    """Pull KC Entries into the KF Spanner graph as DataObjects.

    Args:
        project_id:         GCP project owning the KC catalog.
        location:           KC location (default europe-west1).
        entry_group_id:     informational; the entry name carries its own group.
        subscription_name:  default Pub/Sub subscription for streaming mode.
        dataplex_client:    pre-built `CatalogServiceClient` (tests inject mock).
        subscriber_client:  pre-built `pubsub_v1.SubscriberClient` (tests).
        writer:             callable(graph_json, doc_id, ...) -> dict — defaults
                            to `services.graph_writer.write_graph_to_spanner`.
        embedder:           callable([{"name": str}]) -> [embedding] — defaults
                            to `services.document_chunker.compute_entity_embeddings`.
    """

    def __init__(
        self,
        project_id: str,
        location: str = "europe-west1",
        entry_group_id: str = "kf-import",
        subscription_name: str | None = None,
        dataplex_client: Any = None,
        subscriber_client: Any = None,
        writer: Callable[..., dict] | None = None,
        embedder: Callable[[list[dict]], list[list[float]]] | None = None,
    ):
        self.project_id = project_id
        self.location = location
        self.entry_group_id = entry_group_id
        self.subscription_name = subscription_name
        self._dataplex = dataplex_client
        self._subscriber = subscriber_client
        self._writer = writer
        self._embedder = embedder

    # -- lazy-built clients ------------------------------------------------

    @property
    def dataplex(self) -> Any:
        if self._dataplex is None:
            from google.cloud import dataplex_v1  # type: ignore

            self._dataplex = dataplex_v1.CatalogServiceClient()
        return self._dataplex

    @property
    def subscriber(self) -> Any:
        if self._subscriber is None:
            from google.cloud import pubsub_v1  # type: ignore

            self._subscriber = pubsub_v1.SubscriberClient()
        return self._subscriber

    @property
    def writer(self) -> Callable[..., dict]:
        if self._writer is None:
            from services.graph_writer import write_graph_to_spanner  # type: ignore

            self._writer = write_graph_to_spanner
        return self._writer

    @property
    def embedder(self) -> Callable[[list[dict]], list[list[float]]]:
        if self._embedder is None:
            from services.document_chunker import compute_entity_embeddings  # type: ignore

            self._embedder = compute_entity_embeddings
        return self._embedder

    # -- helpers -----------------------------------------------------------

    def _check_enabled(self) -> None:
        if not _is_enabled():
            raise KCImportDisabled(
                "KC import is disabled. Set KC_IMPORT_ENABLED=true to opt in."
            )

    def _fetch_entry(self, entry_name: str) -> Any:
        """Fetch an Entry from Dataplex. Returns the raw client response."""
        return self.dataplex.get_entry(name=entry_name)

    @staticmethod
    def _entry_attr(entry: Any, key: str, default: Any = None) -> Any:
        """Read attribute or dict key from an Entry (mocked or real)."""
        if entry is None:
            return default
        if isinstance(entry, dict):
            return entry.get(key, default)
        return getattr(entry, key, default)

    def _build_node_payload(
        self, entry_name: str, entry: Any
    ) -> dict[str, Any] | None:
        """Build a graph_writer-compatible payload for a single Entry.

        Returns None if the entry should be skipped (non-whitelisted type).
        """
        entry_type_full = self._entry_attr(entry, "entry_type") or self._entry_attr(
            entry, "entryType"
        )
        entry_type_short = _extract_entry_type_short(entry_type_full)

        if entry_type_short not in KC_ENTRY_TYPE_WHITELIST:
            logger.info(
                "Skipping KC entry %s: entry_type %r not in whitelist",
                entry_name,
                entry_type_short,
            )
            return None

        # entry_source carries display metadata (Dataplex's normalized form)
        source = self._entry_attr(entry, "entry_source") or self._entry_attr(
            entry, "entrySource"
        )
        fqn = (
            self._entry_attr(entry, "fully_qualified_name")
            or self._entry_attr(entry, "fullyQualifiedName")
            or self._entry_attr(source, "resource")
            or entry_name
        )
        display_name = (
            self._entry_attr(source, "display_name")
            or self._entry_attr(source, "displayName")
            or fqn
        )
        description = self._entry_attr(source, "description") or ""

        aspect = {
            "entry_name": entry_name,
            "entry_type": entry_type_short,
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "source_system": SOURCE_SYSTEM,
        }

        return {
            "entity_id": make_entity_id(entry_name),
            "name": fqn,
            "display_name": display_name,
            "description": description,
            "entry_type": entry_type_short,
            "aspect": aspect,
            "embedding_seed": f"{display_name} {description}".strip(),
            "source_doc_id": f"kc:{entry_name}",
        }

    def _write_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Hand off the mapped payload to the graph writer.

        Builds a graph_json shaped like extract_graph output (a single
        DataObject node, no edges) plus the imported aspect serialized as
        JSON in the node `details` field. Idempotent thanks to the
        deterministic doc_id (== source_doc_id == kc:<entry_name>).
        """
        # Compute embedding for the single entity (batch of 1).
        try:
            embeddings = self.embedder(
                [{"name": payload["embedding_seed"] or payload["display_name"]}]
            )
            doc_embedding = embeddings[0] if embeddings else []
        except Exception as exc:  # pragma: no cover - exercised when client misconfigured
            logger.warning(
                "Embedding failed for KC entry %s: %s — using zero vector",
                payload["source_doc_id"],
                exc,
            )
            doc_embedding = []

        # Build a minimal extract_graph-style dict the writer understands.
        graph_json = {
            "extracted_nodes": [f"DataObject:{payload['name']}"],
            "extracted_edges": [],
            # Out-of-band hint carrying the aspect for downstream consumers
            # that want to surface "imported from KC" provenance.
            "kc_aspect": payload["aspect"],
        }

        result = self.writer(
            graph_json=graph_json,
            doc_id=payload["source_doc_id"],
            doc_title=payload["display_name"],
            doc_summary=json.dumps(payload["aspect"]),
            doc_embedding=doc_embedding,
        )
        return result

    # -- public API --------------------------------------------------------

    def import_entry(self, entry_name: str) -> dict[str, Any]:
        """Fetch one Entry from KC and write it into the KF graph."""
        self._check_enabled()

        entry = self._fetch_entry(entry_name)
        payload = self._build_node_payload(entry_name, entry)
        if payload is None:
            return {
                "entry_name": entry_name,
                "status": "skipped",
                "reason": "entry_type_not_whitelisted",
            }

        write_summary = self._write_payload(payload)
        return {
            "entry_name": entry_name,
            "entity_id": payload["entity_id"],
            "status": "imported",
            "writer": write_summary,
            "aspect": payload["aspect"],
        }

    def import_batch(self, entry_names: list[str]) -> dict[str, Any]:
        """Import a list of Entries; collects per-entry results."""
        self._check_enabled()

        results: list[dict[str, Any]] = []
        imported = 0
        skipped = 0
        failed = 0
        for name in entry_names:
            try:
                r = self.import_entry(name)
            except KCImportDisabled:
                raise
            except Exception as exc:  # noqa: BLE001 - surface per-entry failures
                logger.exception("KC import failed for %s", name)
                results.append({"entry_name": name, "status": "failed", "error": str(exc)})
                failed += 1
                continue
            results.append(r)
            if r["status"] == "imported":
                imported += 1
            elif r["status"] == "skipped":
                skipped += 1
        return {
            "total": len(entry_names),
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "results": results,
        }

    # -- Pub/Sub: change-feed consumption ----------------------------------

    @staticmethod
    def _extract_entry_name_from_message(message: Any) -> str | None:
        """Parse a Dataplex change-event Pub/Sub message to find an entry name.

        Dataplex publishes events with a JSON payload containing one of
        `entry.name`, `asset.name`, or a top-level `name`. We tolerate all
        three so the importer works against multiple change-feed flavours.
        """
        data = getattr(message, "data", b"") or b""
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                return None
        try:
            payload = json.loads(data) if data else {}
        except json.JSONDecodeError:
            logger.warning("Pub/Sub message data is not valid JSON; skipping")
            return None

        if not isinstance(payload, dict):
            return None
        for path in (("entry", "name"), ("asset", "name"), ("name",)):
            cur: Any = payload
            for key in path:
                if not isinstance(cur, dict) or key not in cur:
                    cur = None
                    break
                cur = cur[key]
            if isinstance(cur, str) and cur:
                return cur
        # Fallback: attribute on the message itself
        attrs = getattr(message, "attributes", None) or {}
        try:
            return attrs.get("entry_name") or attrs.get("name") or None
        except AttributeError:
            return None

    def subscribe(
        self,
        subscription_name: str | None = None,
        max_messages: int = 100,
    ) -> dict[str, Any]:
        """One-shot pull from a Pub/Sub subscription.

        Acks messages whose entry was imported (or explicitly skipped). Nacks
        on import failure so Pub/Sub redelivers. Returns counts; intended for
        cron-style invocation.
        """
        self._check_enabled()

        sub = subscription_name or self.subscription_name
        if not sub:
            raise ValueError(
                "subscription_name required (pass arg or set KC_IMPORT_SUBSCRIPTION)"
            )

        response = self.subscriber.pull(
            request={"subscription": sub, "max_messages": max_messages},
            timeout=30.0,
        )
        received = list(getattr(response, "received_messages", []) or [])

        acked = 0
        nacked = 0
        for received_msg in received:
            message = getattr(received_msg, "message", received_msg)
            ack_id = getattr(received_msg, "ack_id", None)
            entry_name = self._extract_entry_name_from_message(message)
            if not entry_name:
                # Malformed payload — ack to avoid poison-pill loops; logged.
                logger.warning("Pub/Sub message lacks entry name; acking anyway")
                self._ack(sub, ack_id, message)
                acked += 1
                continue
            try:
                self.import_entry(entry_name)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Import failed for %s — nacking for redelivery", entry_name
                )
                self._nack(sub, ack_id, message)
                nacked += 1
                continue
            self._ack(sub, ack_id, message)
            acked += 1

        return {
            "subscription": sub,
            "received": len(received),
            "acked": acked,
            "nacked": nacked,
        }

    def _ack(self, subscription: str, ack_id: str | None, message: Any) -> None:
        """Acknowledge via subscriber.acknowledge OR message.ack (streaming)."""
        if hasattr(message, "ack") and ack_id is None:
            message.ack()
            return
        if ack_id is not None:
            try:
                self.subscriber.acknowledge(
                    request={"subscription": subscription, "ack_ids": [ack_id]}
                )
                return
            except Exception:  # noqa: BLE001 - fall through to message.ack
                logger.debug("subscriber.acknowledge failed; falling back to message.ack")
        if hasattr(message, "ack"):
            message.ack()

    def _nack(self, subscription: str, ack_id: str | None, message: Any) -> None:
        """Negative-ack so Pub/Sub redelivers. Streaming uses message.nack()."""
        if hasattr(message, "nack") and ack_id is None:
            message.nack()
            return
        if ack_id is not None:
            try:
                self.subscriber.modify_ack_deadline(
                    request={
                        "subscription": subscription,
                        "ack_ids": [ack_id],
                        "ack_deadline_seconds": 0,
                    }
                )
                return
            except Exception:  # noqa: BLE001
                logger.debug("modify_ack_deadline failed; falling back to message.nack")
        if hasattr(message, "nack"):
            message.nack()

    def subscribe_streaming(
        self,
        subscription_name: str | None = None,
        callback: Callable[[Any], None] | None = None,
    ) -> None:
        """Long-running streaming pull (daemon mode).

        Wires `subscriber.subscribe(subscription, callback)` and blocks on the
        returned StreamingPullFuture. Callers may pass a custom `callback`; the
        default uses `import_entry` and acks/nacks like `subscribe()`.
        """
        self._check_enabled()

        sub = subscription_name or self.subscription_name
        if not sub:
            raise ValueError(
                "subscription_name required (pass arg or set KC_IMPORT_SUBSCRIPTION)"
            )

        def _default_callback(message: Any) -> None:
            entry_name = self._extract_entry_name_from_message(message)
            if not entry_name:
                logger.warning("Streaming message lacks entry name; acking anyway")
                if hasattr(message, "ack"):
                    message.ack()
                return
            try:
                self.import_entry(entry_name)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Streaming import failed for %s — nacking", entry_name
                )
                if hasattr(message, "nack"):
                    message.nack()
                return
            if hasattr(message, "ack"):
                message.ack()

        cb = callback or _default_callback
        future = self.subscriber.subscribe(sub, callback=cb)
        logger.info("KC importer streaming on %s", sub)
        try:
            # Blocks forever; exits on KeyboardInterrupt or cancel().
            future.result()
        except KeyboardInterrupt:  # pragma: no cover - daemon shutdown path
            future.cancel()
            future.result()


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m services.kc_importer",
        description="Import Knowledge Catalog Entries into the KnowledgeForge graph.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single batch over --entries and exit (no streaming).",
    )
    parser.add_argument(
        "--entries",
        nargs="+",
        default=[],
        help="Fully qualified KC entry names to import (used with --once).",
    )
    parser.add_argument(
        "--subscription",
        default=os.getenv("KC_IMPORT_SUBSCRIPTION", ""),
        help="Pub/Sub subscription (streaming mode). Defaults to $KC_IMPORT_SUBSCRIPTION.",
    )
    args = parser.parse_args(argv)

    project = os.getenv("DATAPLEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        parser.error("DATAPLEX_PROJECT or GOOGLE_CLOUD_PROJECT must be set")

    importer = KCImporter(
        project_id=project,
        location=os.getenv("KC_LOCATION", "europe-west1"),
        entry_group_id=os.getenv("KC_ENTRY_GROUP_ID", "kf-import"),
        subscription_name=args.subscription or None,
    )

    try:
        if args.once:
            if not args.entries:
                parser.error("--once requires at least one --entries argument")
            summary = importer.import_batch(args.entries)
            print(
                f"Imported {summary['imported']}/{summary['total']} "
                f"(skipped={summary['skipped']}, failed={summary['failed']})"
            )
            return 0 if summary["failed"] == 0 else 1
        if not args.subscription:
            parser.error("either --once or --subscription must be provided")
        importer.subscribe_streaming(args.subscription)
        return 0
    except KCImportDisabled as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
