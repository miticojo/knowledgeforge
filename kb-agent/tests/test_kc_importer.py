"""Unit tests for services.kc_importer (Milestone C — KC reverse importer).

Mocks both the Dataplex CatalogServiceClient and the Pub/Sub SubscriberClient.
The optional GCP SDKs are gated via `importorskip` so the suite stays green in
environments without the `kc` extras installed.
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("google.cloud.dataplex_v1")
pytest.importorskip("google.cloud.pubsub_v1")

from services import kc_importer  # noqa: E402
from services.kc_importer import (  # noqa: E402
    KCImportDisabled,
    KCImporter,
    KC_ENTRY_TYPE_WHITELIST,
    make_entity_id,
)


PROJECT = "test-project"
ENTRY_NAME = (
    "projects/test-project/locations/europe-west1/entryGroups/kc/"
    "entries/bigquery-table-foo"
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_entry(entry_type_short: str = "bigquery-table", *, fqn: str = "bq://proj.ds.tbl") -> SimpleNamespace:
    """Build a fake Dataplex Entry that quacks like the real proto."""
    return SimpleNamespace(
        name=ENTRY_NAME,
        entry_type=(
            f"projects/{PROJECT}/locations/europe-west1/entryTypes/{entry_type_short}"
        ),
        fully_qualified_name=fqn,
        entry_source=SimpleNamespace(
            resource=fqn,
            display_name="My Table",
            description="A test table",
        ),
    )


@pytest.fixture
def mock_dataplex():
    return MagicMock()


@pytest.fixture
def mock_subscriber():
    return MagicMock()


@pytest.fixture
def mock_writer():
    return MagicMock(return_value={"doc_id": "kc:x", "entities_total": 1})


@pytest.fixture
def mock_embedder():
    # Return one 768-dim zero vector per input
    def _embed(items):
        return [[0.0] * 768 for _ in items]
    return MagicMock(side_effect=_embed)


@pytest.fixture
def importer(mock_dataplex, mock_subscriber, mock_writer, mock_embedder):
    return KCImporter(
        project_id=PROJECT,
        location="europe-west1",
        dataplex_client=mock_dataplex,
        subscriber_client=mock_subscriber,
        writer=mock_writer,
        embedder=mock_embedder,
    )


@pytest.fixture
def enable_kc(monkeypatch):
    monkeypatch.setenv("KC_IMPORT_ENABLED", "true")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_disabled_by_default_raises(monkeypatch, importer):
    monkeypatch.delenv("KC_IMPORT_ENABLED", raising=False)
    with pytest.raises(KCImportDisabled):
        importer.import_entry(ENTRY_NAME)
    with pytest.raises(KCImportDisabled):
        importer.import_batch([ENTRY_NAME])
    with pytest.raises(KCImportDisabled):
        importer.subscribe("projects/p/subscriptions/s")


def test_import_entry_writes_dataobject(
    enable_kc, importer, mock_dataplex, mock_writer
):
    mock_dataplex.get_entry.return_value = _make_entry("bigquery-table")
    result = importer.import_entry(ENTRY_NAME)

    assert result["status"] == "imported"
    assert result["entity_id"] == make_entity_id(ENTRY_NAME)

    # writer called once with a DataObject node and source_doc_id == kc:<entry>
    assert mock_writer.call_count == 1
    kwargs = mock_writer.call_args.kwargs
    assert kwargs["doc_id"] == f"kc:{ENTRY_NAME}"
    assert kwargs["graph_json"]["extracted_nodes"] == ["DataObject:bq://proj.ds.tbl"]
    assert kwargs["graph_json"]["kc_aspect"]["entry_type"] == "bigquery-table"
    assert kwargs["graph_json"]["kc_aspect"]["source_system"] == "google-knowledge-catalog"


def test_import_entry_skips_unknown_entry_type(
    enable_kc, importer, mock_dataplex, mock_writer
):
    mock_dataplex.get_entry.return_value = _make_entry("looker-dashboard")
    result = importer.import_entry(ENTRY_NAME)
    assert result["status"] == "skipped"
    assert result["reason"] == "entry_type_not_whitelisted"
    mock_writer.assert_not_called()


def test_import_batch_idempotent(enable_kc, importer, mock_dataplex):
    mock_dataplex.get_entry.return_value = _make_entry("bigquery-table")
    a = importer.import_batch([ENTRY_NAME])
    b = importer.import_batch([ENTRY_NAME])

    id_a = a["results"][0]["entity_id"]
    id_b = b["results"][0]["entity_id"]
    assert id_a == id_b
    # Validate the deterministic UUID v5 contract directly.
    assert id_a == str(uuid.uuid5(uuid.NAMESPACE_DNS, ENTRY_NAME))


def test_import_batch_collects_failures(
    enable_kc, importer, mock_dataplex
):
    """A per-entry failure should not break the batch — it's recorded."""
    def _flaky(name):
        if "boom" in name:
            raise RuntimeError("kapow")
        return _make_entry("bigquery-table")

    mock_dataplex.get_entry.side_effect = lambda name: _flaky(name)
    summary = importer.import_batch([ENTRY_NAME, ENTRY_NAME + "-boom"])
    assert summary["total"] == 2
    assert summary["imported"] == 1
    assert summary["failed"] == 1


def _make_received_message(entry_name: str | None) -> SimpleNamespace:
    payload = json.dumps({"entry": {"name": entry_name}}) if entry_name else "{}"
    msg = MagicMock()
    msg.data = payload.encode("utf-8")
    msg.attributes = {}
    return SimpleNamespace(ack_id="ack-1", message=msg)


def test_subscribe_acks_on_success(
    enable_kc, importer, mock_dataplex, mock_subscriber
):
    mock_dataplex.get_entry.return_value = _make_entry("bigquery-table")
    received = _make_received_message(ENTRY_NAME)
    mock_subscriber.pull.return_value = SimpleNamespace(received_messages=[received])

    result = importer.subscribe("projects/p/subscriptions/s")

    assert result["acked"] == 1
    assert result["nacked"] == 0
    # Either subscriber.acknowledge OR message.ack should have been used.
    ack_called = mock_subscriber.acknowledge.called or received.message.ack.called
    assert ack_called


def test_subscribe_nacks_on_failure(
    enable_kc, importer, mock_dataplex, mock_subscriber
):
    mock_dataplex.get_entry.side_effect = RuntimeError("dataplex down")
    received = _make_received_message(ENTRY_NAME)
    mock_subscriber.pull.return_value = SimpleNamespace(received_messages=[received])

    result = importer.subscribe("projects/p/subscriptions/s")

    assert result["nacked"] == 1
    assert result["acked"] == 0
    nack_called = (
        mock_subscriber.modify_ack_deadline.called or received.message.nack.called
    )
    assert nack_called


def test_subscribe_streaming_invokes_callback(
    enable_kc, importer, mock_dataplex, mock_subscriber
):
    mock_dataplex.get_entry.return_value = _make_entry("bigquery-table")

    captured: dict = {}

    def _fake_subscribe(sub, callback):
        captured["sub"] = sub
        captured["callback"] = callback
        # Simulate a single inbound message immediately.
        msg = MagicMock()
        msg.data = json.dumps({"entry": {"name": ENTRY_NAME}}).encode("utf-8")
        msg.attributes = {}
        callback(msg)
        future = MagicMock()
        future.result.return_value = None
        return future

    mock_subscriber.subscribe.side_effect = _fake_subscribe
    importer.subscribe_streaming("projects/p/subscriptions/s")

    assert captured["sub"] == "projects/p/subscriptions/s"
    # Default callback should have invoked import_entry which in turn called the writer.
    assert mock_dataplex.get_entry.called


def test_whitelist_contains_expected_types():
    """Sanity: the whitelist is what we documented."""
    for t in (
        "bigquery-table",
        "spanner-database",
        "alloydb-postgres-table",
    ):
        assert t in KC_ENTRY_TYPE_WHITELIST


def test_module_imports_clean_without_flag(monkeypatch):
    """The module must import + KCImporter() must construct with the flag off."""
    monkeypatch.delenv("KC_IMPORT_ENABLED", raising=False)
    KCImporter(project_id="x", location="y")  # must not raise
