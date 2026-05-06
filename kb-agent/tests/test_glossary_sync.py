"""Unit tests for services.glossary_sync (Milestone D).

The Dataplex SDK is treated as optional (importorskip). All Spanner reads /
writes and KC client calls are mocked — no GCP, no Spanner emulator needed.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("google.cloud.dataplex_v1")

from services import glossary_sync  # noqa: E402
from services.glossary_sync import (  # noqa: E402
    DEFAULT_GLOSSARY_ID,
    GlossarySync,
    LAYER_TO_CATEGORY,
    make_business_object_id,
    make_term_id,
)


PROJECT = "test-project"
GLOSSARY = DEFAULT_GLOSSARY_ID
DOC_ID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def sync(mock_client):
    return GlossarySync(
        project_id=PROJECT,
        location="europe-west1",
        glossary_id=GLOSSARY,
        dataplex_client=mock_client,
    )


@pytest.fixture
def fixture_business_objects():
    return [
        {
            "object_id": "bo-1",
            "object_name": "Customer",
            "description": "An individual or organization that buys goods.",
            "archimate_layer": "Business",
            "source_doc_id": DOC_ID,
            "synonyms": ["Client", "Buyer"],
        },
        {
            "object_id": "bo-2",
            "object_name": "Invoice",
            "description": "A document requesting payment.",
            "archimate_layer": "Business",
            "source_doc_id": DOC_ID,
            "synonyms": [],
        },
    ]


# ---------------------------------------------------------------------------
# ID determinism
# ---------------------------------------------------------------------------


def test_make_term_id_is_deterministic_uuid_v5():
    a = make_term_id(GLOSSARY, "Customer")
    b = make_term_id(GLOSSARY, "Customer")
    assert a == b
    expected = str(
        uuid.uuid5(
            uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"),
            f"{GLOSSARY}:Customer",
        )
    )
    assert a == expected


def test_make_business_object_id_is_deterministic_uuid_v5():
    term_id = make_term_id(GLOSSARY, "Customer")
    a = make_business_object_id(GLOSSARY, term_id)
    b = make_business_object_id(GLOSSARY, term_id)
    assert a == b


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------


def test_push_creates_one_term_per_business_object(
    sync, mock_client, fixture_business_objects
):
    with patch.object(
        sync, "_read_business_objects", return_value=fixture_business_objects
    ):
        summary = sync.push(doc_id=DOC_ID)

    assert summary["terms_total"] == 2
    assert mock_client.create_glossary_term.call_count == 2

    # First call: Customer with deterministic id and Business category.
    first = mock_client.create_glossary_term.call_args_list[0]
    expected_term_id = make_term_id(GLOSSARY, "Customer")
    assert first.kwargs["term_id"] == expected_term_id
    assert first.kwargs["parent"].endswith(f"/glossaries/{GLOSSARY}")
    term = first.kwargs["term"]
    assert term["display_name"] == "Customer"
    assert term["definition"].startswith("An individual")
    # Synonyms are sorted + de-duplicated.
    assert term["synonyms"] == ["Buyer", "Client"]
    assert term["parent_category"].endswith(
        f"/categories/{LAYER_TO_CATEGORY['Business']}"
    )


def test_push_is_idempotent_same_term_ids(
    sync, mock_client, fixture_business_objects
):
    with patch.object(
        sync, "_read_business_objects", return_value=fixture_business_objects
    ):
        first = sync.push(doc_id=DOC_ID)
        second = sync.push(doc_id=DOC_ID)

    ids_first = [t["name"] for t in first["terms"]]
    ids_second = [t["name"] for t in second["terms"]]
    assert ids_first == ids_second


def test_push_handles_missing_description(sync, mock_client):
    rows = [
        {
            "object_id": "bo-x",
            "object_name": "Account",
            "description": None,
            "archimate_layer": "Business",
            "source_doc_id": DOC_ID,
            "synonyms": [],
        }
    ]
    with patch.object(sync, "_read_business_objects", return_value=rows):
        summary = sync.push(doc_id=DOC_ID)

    term = summary["terms"][0]
    assert term["definition"] == ""
    assert term["synonyms"] == []


def test_push_synonym_conflict_merges_on_already_exists(sync, mock_client):
    """When the term already exists in KC, synonyms must be merged (union)."""
    rows = [
        {
            "object_id": "bo-1",
            "object_name": "Customer",
            "description": "Local description.",
            "archimate_layer": "Business",
            "source_doc_id": DOC_ID,
            "synonyms": ["Client"],
        }
    ]

    class AlreadyExists(Exception):
        pass

    mock_client.create_glossary_term.side_effect = AlreadyExists(
        "term already exists"
    )
    # KC side already has a different synonym, "Patron".
    mock_client.get_glossary_term.return_value = {
        "name": sync._term_name(make_term_id(GLOSSARY, "Customer")),
        "display_name": "Customer",
        "definition": "Existing.",
        "parent_category": "",
        "synonyms": ["Patron"],
    }

    with patch.object(sync, "_read_business_objects", return_value=rows):
        sync.push(doc_id=DOC_ID)

    # update_glossary_term must be called with the *union* of synonyms.
    assert mock_client.update_glossary_term.call_count == 1
    updated = mock_client.update_glossary_term.call_args.kwargs["term"]
    assert updated["synonyms"] == ["Client", "Patron"]


def test_push_duplicate_names_collapse_to_same_term_id(sync, mock_client):
    """Two BusinessObjects with the same name must hit the same term_id."""
    rows = [
        {
            "object_id": "bo-1",
            "object_name": "Customer",
            "description": "A.",
            "archimate_layer": "Business",
            "source_doc_id": DOC_ID,
            "synonyms": [],
        },
        {
            "object_id": "bo-2",
            "object_name": "Customer",
            "description": "B.",
            "archimate_layer": "Business",
            "source_doc_id": DOC_ID,
            "synonyms": [],
        },
    ]
    with patch.object(sync, "_read_business_objects", return_value=rows):
        summary = sync.push(doc_id=DOC_ID)

    ids = {t["name"] for t in summary["terms"]}
    assert len(ids) == 1


# ---------------------------------------------------------------------------
# pull
# ---------------------------------------------------------------------------


def _kc_term(name: str, definition: str, synonyms: list[str], category: str = "business"):
    return {
        "name": (
            f"projects/{PROJECT}/locations/europe-west1/glossaries/"
            f"{GLOSSARY}/terms/{make_term_id(GLOSSARY, name)}"
        ),
        "display_name": name,
        "definition": definition,
        "parent_category": (
            f"projects/{PROJECT}/locations/europe-west1/glossaries/"
            f"{GLOSSARY}/categories/{category}"
        ),
        "synonyms": synonyms,
    }


def test_pull_creates_business_object_mutations(sync, mock_client):
    terms = [
        _kc_term("Customer", "A buyer.", ["Client"]),
        _kc_term("Client", "Synonym holder.", ["Customer"]),
    ]
    mock_client.list_glossary_terms.return_value = terms

    captured = {}

    def fake_batch_write(mutations):
        captured["mutations"] = mutations

    with patch(
        "services.spanner_client.batch_write", side_effect=fake_batch_write
    ):
        summary = sync.pull()

    assert summary["terms_total"] == 2
    assert summary["business_objects"][0]["term_id"] == make_term_id(
        GLOSSARY, "Customer"
    )

    tables = {m[0] for m in captured["mutations"]}
    assert "BusinessObjects" in tables
    assert "Association" in tables  # synonym pair -> Association rows

    # 2 BusinessObjects + 2 Association rows (one per direction).
    bo_rows = next(m for m in captured["mutations"] if m[0] == "BusinessObjects")[2]
    assoc_rows = next(m for m in captured["mutations"] if m[0] == "Association")[2]
    assert len(bo_rows) == 2
    assert len(assoc_rows) == 2

    # Description was carried into the description column (idx 3).
    cols = next(m for m in captured["mutations"] if m[0] == "BusinessObjects")[1]
    desc_idx = cols.index("description")
    assert bo_rows[0][desc_idx] == "A buyer."


def test_pull_skips_dangling_synonym_targets(sync, mock_client):
    """A synonym that doesn't appear as another term in the batch is skipped."""
    terms = [_kc_term("Customer", "A buyer.", ["Patron"])]  # Patron not present
    mock_client.list_glossary_terms.return_value = terms

    captured = {}

    def fake_batch_write(mutations):
        captured["mutations"] = mutations

    with patch(
        "services.spanner_client.batch_write", side_effect=fake_batch_write
    ):
        sync.pull()

    tables = {m[0] for m in captured["mutations"]}
    assert "BusinessObjects" in tables
    assert "Association" not in tables


def test_pull_idempotent_business_object_ids(sync, mock_client):
    terms = [_kc_term("Customer", "A.", [])]
    mock_client.list_glossary_terms.return_value = terms

    captured: list[dict] = []

    def fake_batch_write(mutations):
        captured.append(mutations)

    with patch(
        "services.spanner_client.batch_write", side_effect=fake_batch_write
    ):
        s1 = sync.pull()
        s2 = sync.pull()

    assert (
        s1["business_objects"][0]["business_object_id"]
        == s2["business_objects"][0]["business_object_id"]
    )


# ---------------------------------------------------------------------------
# sync convenience
# ---------------------------------------------------------------------------


def test_sync_both_runs_push_then_pull(sync, mock_client):
    mock_client.list_glossary_terms.return_value = []
    with patch.object(sync, "_read_business_objects", return_value=[]), patch(
        "services.spanner_client.batch_write"
    ):
        out = sync.sync(direction="both", doc_id=DOC_ID)

    assert "push" in out
    assert "pull" in out
    assert out["push"]["terms_total"] == 0
    assert out["pull"]["terms_total"] == 0


def test_sync_push_only(sync, mock_client):
    with patch.object(sync, "_read_business_objects", return_value=[]):
        out = sync.sync(direction="push", doc_id=DOC_ID)
    assert "push" in out and "pull" not in out


def test_sync_pull_only(sync, mock_client):
    mock_client.list_glossary_terms.return_value = []
    with patch("services.spanner_client.batch_write"):
        out = sync.sync(direction="pull")
    assert "pull" in out and "push" not in out
