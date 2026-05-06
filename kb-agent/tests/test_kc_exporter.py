"""Unit tests for services.kc_exporter (Milestone B).

These tests fully mock CatalogServiceClient and the Spanner read layer — no GCP
calls are made. The google-cloud-dataplex package is treated as optional via
`importorskip`, so the suite stays green in environments that haven't installed
the `kc` extra.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

# Skip the whole module if the optional Dataplex SDK isn't installed.
pytest.importorskip("google.cloud.dataplex_v1")

from services import kc_exporter  # noqa: E402  (import after importorskip)
from services.kc_exporter import (  # noqa: E402
    ASPECT_TYPE_PROVENANCE,
    ENTRY_LINK_TYPE_ACCESSES,
    ENTRY_LINK_TYPE_DEFINITION,
    ENTRY_LINK_TYPE_REALIZES,
    ENTRY_TYPE_DATA_OBJECT,
    KCExportDisabled,
    KCExporter,
    make_entry_id,
)


DOC_ID = "11111111-1111-1111-1111-111111111111"
PROJECT = "test-project"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_kc(monkeypatch):
    """Most tests assume KC export is enabled; individual tests can override."""
    monkeypatch.setenv("KC_SYNC_ENABLED", "true")


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def fixture_graph():
    """A small graph: one DataObject + one Access edge (App -> Data)."""
    return {
        "data_objects": [
            {
                "model_id": "do-1",
                "model_name": "CustomerRecord",
                "source_doc_id": DOC_ID,
            }
        ],
        "business_objects": [],
        "accesses": [
            {
                "source_id": "ac-1",
                "source_type": "ApplicationComponent",
                "source_name": "BillingApp",
                "target_id": "do-1",
                "target_type": "DataObject",
                "target_name": "CustomerRecord",
                "access_type": "ReadWrite",
                "confidence": "EXTRACTED",
            }
        ],
        "realizations": [],
    }


@pytest.fixture
def exporter(mock_client):
    return KCExporter(
        project_id=PROJECT,
        location="europe-west1",
        entry_group_id="kf-import",
        dataplex_client=mock_client,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_make_entry_id_is_deterministic_uuid_v5():
    a = make_entry_id(DOC_ID, "CustomerRecord")
    b = make_entry_id(DOC_ID, "CustomerRecord")
    assert a == b
    # UUID v5 against NAMESPACE_DNS with the same name MUST match this exact value.
    expected = str(uuid.uuid5(uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"),
                              f"{DOC_ID}:CustomerRecord"))
    assert a == expected


def test_export_doc_disabled_raises(monkeypatch, exporter):
    monkeypatch.setenv("KC_SYNC_ENABLED", "false")
    with pytest.raises(KCExportDisabled):
        exporter.export_doc(DOC_ID)


def test_export_doc_creates_entry_and_link(mock_client, exporter, fixture_graph):
    with patch.object(exporter, "_read_graph", return_value=fixture_graph):
        summary = exporter.export_doc(DOC_ID)

    # 1 DataObject Entry, 1 Access EntryLink
    assert summary["entries_total"] == 1
    assert summary["entry_links_total"] == 1

    # create_entry called once with the deterministic UUID v5
    assert mock_client.create_entry.call_count == 1
    call = mock_client.create_entry.call_args
    expected_entry_id = make_entry_id(DOC_ID, "CustomerRecord")
    assert call.kwargs["entry_id"] == expected_entry_id
    assert call.kwargs["parent"].endswith("/entryGroups/kf-import")
    entry = call.kwargs["entry"]
    assert ENTRY_TYPE_DATA_OBJECT in entry["entry_type"]

    # create_entry_link with kf-accesses linking App -> Data
    assert mock_client.create_entry_link.call_count == 1
    link_call = mock_client.create_entry_link.call_args
    link = link_call.kwargs["entry_link"]
    assert ENTRY_LINK_TYPE_ACCESSES in link["entry_link_type"]
    refs = link["entry_references"]
    assert refs[0]["type"] == "SOURCE"
    assert refs[1]["type"] == "TARGET"
    # Target endpoint must point at the same DataObject entry id
    assert refs[1]["name"].endswith(expected_entry_id)


def test_provenance_aspect_includes_confidence_and_source_doc(
    mock_client, exporter, fixture_graph
):
    with patch.object(exporter, "_read_graph", return_value=fixture_graph):
        summary = exporter.export_doc(DOC_ID)

    entry = summary["entries"][0]
    aspects = entry["aspects"]
    assert ASPECT_TYPE_PROVENANCE in aspects
    data = aspects[ASPECT_TYPE_PROVENANCE]["data"]
    assert data["confidence"] == "EXTRACTED"
    assert data["source_doc_id"] == DOC_ID


def test_export_is_idempotent(mock_client, exporter, fixture_graph):
    """Running the export twice must produce identical create_* call payloads.

    The second invocation may either re-create (if the mock client doesn't
    raise) or fall back to update — what matters for idempotency is that the
    *entry_id* (and therefore the resulting KC resource name) is stable.
    """
    with patch.object(exporter, "_read_graph", return_value=fixture_graph):
        first = exporter.export_doc(DOC_ID)
        second = exporter.export_doc(DOC_ID)

    assert first["entries"][0]["name"] == second["entries"][0]["name"]
    assert first["entry_links"][0]["name"] == second["entry_links"][0]["name"]

    # Both invocations attempted to create_entry with the SAME entry_id.
    entry_ids = [c.kwargs["entry_id"] for c in mock_client.create_entry.call_args_list]
    assert len(entry_ids) == 2
    assert entry_ids[0] == entry_ids[1]


def test_realization_dataobject_to_businessobject_emits_definition_link(
    mock_client, exporter
):
    graph = {
        "data_objects": [
            {"model_id": "do-1", "model_name": "CustomerRecord", "source_doc_id": DOC_ID}
        ],
        "business_objects": [
            {"object_id": "bo-1", "object_name": "Customer", "source_doc_id": DOC_ID}
        ],
        "accesses": [],
        "realizations": [
            {
                "source_id": "do-1",
                "source_type": "DataObject",
                "source_name": "CustomerRecord",
                "target_id": "bo-1",
                "target_type": "BusinessObject",
                "target_name": "Customer",
                "details": "",
                "confidence": "INFERRED",
            }
        ],
    }
    with patch.object(exporter, "_read_graph", return_value=graph):
        summary = exporter.export_doc(DOC_ID)

    link_types = [link["entry_link_type"] for link in summary["entry_links"]]
    assert any(ENTRY_LINK_TYPE_DEFINITION in t for t in link_types)
    assert summary["entry_links_total"] == 1


def test_realization_component_to_dataobject_emits_realizes_link(
    mock_client, exporter
):
    graph = {
        "data_objects": [
            {"model_id": "do-1", "model_name": "CustomerRecord", "source_doc_id": DOC_ID}
        ],
        "business_objects": [],
        "accesses": [],
        "realizations": [
            {
                "source_id": "ac-1",
                "source_type": "ApplicationComponent",
                "source_name": "BillingApp",
                "target_id": "do-1",
                "target_type": "DataObject",
                "target_name": "CustomerRecord",
                "details": "",
                "confidence": "EXTRACTED",
            }
        ],
    }
    with patch.object(exporter, "_read_graph", return_value=graph):
        summary = exporter.export_doc(DOC_ID)

    link_types = [link["entry_link_type"] for link in summary["entry_links"]]
    assert any(ENTRY_LINK_TYPE_REALIZES in t for t in link_types)
