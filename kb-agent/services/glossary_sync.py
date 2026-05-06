"""Bidirectional glossary bridge: KF BusinessObject <-> KC Glossary Term.

Milestone D of the Knowledge Catalog Bridge. Sits alongside
``kc_exporter.py`` (Milestone B, KF -> KC for DataObjects) and the planned
importer (Milestone C, KC -> KF for technology assets).

Mapping (symmetric, conflict-free design):

    ArchiMate BusinessObject    <-> KC Glossary Term
    archimate_layer             -> Glossary Category
                                   (Strategy/Business/Application/Technology/Motivation)
    `synonyms` aspect           <-> Term `synonyms` list (union on conflict)
    `description` aspect        <-> Term `definition`        (last-write-wins)
    Related-term references     <-> ArchiMate `Association` edges

Idempotency:

    term_id          = uuid5(NAMESPACE_DNS, f"{glossary_id}:{business_object_name}")
    business_object  = uuid5(NAMESPACE_DNS, f"glossary:{glossary_id}:{term_id}")

The same name in the same glossary always resolves to the same UUID, so
running ``sync`` repeatedly is safe.

Conflict policy:
    - description / definition: last-write-wins
    - synonyms: union (never lose a synonym)
    - never delete on the opposite side (additive sync only)

CLI::

    python -m kb_agent.services.glossary_sync --direction both --doc-id <id>

Required env: ``DATAPLEX_PROJECT``/``GOOGLE_CLOUD_PROJECT``.
Optional env: ``KC_LOCATION`` (default europe-west1), ``KC_GLOSSARY_ID``
(default kf-glossary).
"""
from __future__ import annotations

import argparse
import logging
import os
import uuid
from typing import Any, Iterable, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_GLOSSARY_ID = "kf-glossary"
DEFAULT_LOCATION = "europe-west1"

# ArchiMate layer -> Glossary Category id (slugified)
LAYER_TO_CATEGORY: dict[str, str] = {
    "Strategy": "strategy",
    "Business": "business",
    "Application": "application",
    "Technology": "technology",
    "Motivation": "motivation",
}

CATEGORY_TO_LAYER: dict[str, str] = {v: k for k, v in LAYER_TO_CATEGORY.items()}


# ---------------------------------------------------------------------------
# Deterministic ID helpers
# ---------------------------------------------------------------------------


def make_term_id(glossary_id: str, business_object_name: str) -> str:
    """Stable KC GlossaryTerm id derived from BusinessObject name."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_DNS, f"{glossary_id}:{business_object_name}")
    )


def make_business_object_id(glossary_id: str, term_id: str) -> str:
    """Stable BusinessObject UUID derived from a KC GlossaryTerm id."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_DNS, f"glossary:{glossary_id}:{term_id}")
    )


# ---------------------------------------------------------------------------
# GlossarySync
# ---------------------------------------------------------------------------


class GlossarySync:
    """Bidirectional sync between KF BusinessObjects and a KC Glossary.

    Args:
        project_id: GCP project that owns the Knowledge Catalog glossary.
        location: KC location (default ``europe-west1``).
        glossary_id: target Glossary id (default ``kf-glossary``).
        dataplex_client: pre-built client (mostly for tests). When ``None`` a
            real ``BusinessGlossaryServiceClient`` is constructed lazily.
    """

    def __init__(
        self,
        project_id: str,
        location: str = DEFAULT_LOCATION,
        glossary_id: str = DEFAULT_GLOSSARY_ID,
        dataplex_client: Any = None,
    ):
        self.project_id = project_id
        self.location = location
        self.glossary_id = glossary_id
        self._client = dataplex_client

    # -- lazy client -------------------------------------------------------

    @property
    def client(self) -> Any:
        if self._client is None:
            from google.cloud import dataplex_v1  # type: ignore

            # The Glossary API is part of the Dataplex Catalog surface.
            # In recent SDKs it is exposed as `BusinessGlossaryServiceClient`;
            # we fall back to `CatalogServiceClient` to remain compatible with
            # versions that fold glossary calls into the catalog client.
            client_cls = getattr(
                dataplex_v1,
                "BusinessGlossaryServiceClient",
                None,
            ) or dataplex_v1.CatalogServiceClient
            self._client = client_cls()
        return self._client

    # -- name helpers ------------------------------------------------------

    def _glossary_name(self) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}"
            f"/glossaries/{self.glossary_id}"
        )

    def _term_name(self, term_id: str) -> str:
        return f"{self._glossary_name()}/terms/{term_id}"

    def _category_name(self, category_id: str) -> str:
        return f"{self._glossary_name()}/categories/{category_id}"

    # -- payload builders --------------------------------------------------

    def _build_term_payload(
        self,
        term_id: str,
        display_name: str,
        layer: str,
        description: str,
        synonyms: Iterable[str],
    ) -> dict[str, Any]:
        category_id = LAYER_TO_CATEGORY.get(layer, LAYER_TO_CATEGORY["Business"])
        # Stable, sorted, de-duplicated synonyms — keeps tests deterministic
        # and lets the merge step on pull treat the list as a set.
        synonyms_list = sorted({s for s in synonyms if s})
        return {
            "name": self._term_name(term_id),
            "display_name": display_name,
            "definition": description or "",
            "parent_category": self._category_name(category_id),
            "synonyms": synonyms_list,
            "_kf": {  # internal hint for tests / debugging — not sent to GCP
                "layer": layer,
                "business_object_name": display_name,
            },
        }

    # -- Spanner reads (push side) ----------------------------------------

    def _read_business_objects(
        self, doc_id: str | None
    ) -> list[dict[str, Any]]:
        """Read BusinessObjects (optionally scoped to one source doc).

        Returned rows include any synonyms harvested from Association edges
        between BusinessObjects. We treat an Association whose qualifier is
        ``"synonym"`` as a glossary synonym relation.
        """
        from services.spanner_client import run_query  # type: ignore

        if doc_id:
            bo_rows = run_query(
                "SELECT object_id, object_name, description, archimate_layer, "
                "       source_doc_id "
                "FROM BusinessObjects WHERE source_doc_id = @doc_id",
                params={"doc_id": doc_id},
            )
        else:
            bo_rows = run_query(
                "SELECT object_id, object_name, description, archimate_layer, "
                "       source_doc_id "
                "FROM BusinessObjects",
                params={},
            )

        # Synonyms via Association edges between BusinessObjects.
        synonyms_by_id: dict[str, set[str]] = {}
        if bo_rows:
            ids = [r["object_id"] for r in bo_rows]
            assoc = run_query(
                "SELECT a.source_id, a.target_id, b1.object_name AS src_name, "
                "       b2.object_name AS tgt_name "
                "FROM Association a "
                "JOIN BusinessObjects b1 ON b1.object_id = a.source_id "
                "JOIN BusinessObjects b2 ON b2.object_id = a.target_id "
                "WHERE a.source_type = 'BusinessObject' "
                "  AND a.target_type = 'BusinessObject' "
                "  AND a.association_details = 'synonym' "
                "  AND a.source_id IN UNNEST(@ids)",
                params={"ids": ids},
            )
            for row in assoc:
                synonyms_by_id.setdefault(row["source_id"], set()).add(
                    row["tgt_name"]
                )
                synonyms_by_id.setdefault(row["target_id"], set()).add(
                    row["src_name"]
                )

        for r in bo_rows:
            r["synonyms"] = sorted(synonyms_by_id.get(r["object_id"], set()))
        return bo_rows

    # -- KC reads (pull side) ---------------------------------------------

    def _list_terms(self) -> list[dict[str, Any]]:
        """List GlossaryTerms in the configured glossary.

        Normalizes terms (whether returned as proto messages or dicts) into
        plain dicts with: ``name``, ``display_name``, ``definition``,
        ``parent_category``, ``synonyms``.
        """
        client = self.client
        parent = self._glossary_name()

        # SDK surface varies between versions; fall back across the known
        # spellings rather than committing to one.
        list_fn = (
            getattr(client, "list_glossary_terms", None)
            or getattr(client, "list_terms", None)
        )
        if list_fn is None:
            raise RuntimeError(
                "Dataplex client lacks list_glossary_terms / list_terms"
            )

        raw_terms = list_fn(parent=parent)
        result = []
        for t in raw_terms:
            result.append(_term_to_dict(t))
        return result

    # -- Spanner writes (pull side) ---------------------------------------

    def _build_business_object_mutations(
        self, terms: list[dict[str, Any]]
    ) -> tuple[list[tuple[str, list[str], list[list]]], list[dict]]:
        """Build Spanner mutations for the pull direction.

        Returns (mutations, audit_records) where audit_records mirror the
        rows we wrote (handy for tests + summary).
        """
        from services.tenant_context import SHARED_TENANT  # type: ignore

        bo_rows: list[list[Any]] = []
        assoc_rows: list[list[Any]] = []
        audit: list[dict] = []

        # name -> business_object_id, used to materialize Association rows for
        # synonym pairs in the same pull batch.
        name_to_id: dict[str, str] = {}

        for t in terms:
            term_id = t["name"].rsplit("/", 1)[-1]
            bo_id = make_business_object_id(self.glossary_id, term_id)
            display = t.get("display_name") or ""
            definition = t.get("definition") or ""
            category_id = (t.get("parent_category") or "").rsplit("/", 1)[-1]
            layer = CATEGORY_TO_LAYER.get(category_id, "Business")
            name_to_id[display] = bo_id

            bo_rows.append(
                [
                    bo_id,
                    SHARED_TENANT,
                    display,
                    definition,  # description aspect
                    layer,
                    "",  # source_doc_id — pull-originated, no source doc
                    [0.0] * 768,  # zero-vector embedding (Spanner rejects empty)
                ]
            )
            audit.append(
                {
                    "business_object_id": bo_id,
                    "term_id": term_id,
                    "name": display,
                    "definition": definition,
                    "layer": layer,
                    "synonyms": list(t.get("synonyms") or []),
                }
            )

        # Synonym -> Association(BusinessObject -> BusinessObject, qualifier=synonym).
        # Skipped when the synonym name doesn't appear as a term in this batch
        # (we never invent BusinessObjects we haven't seen).
        for t in terms:
            display = t.get("display_name") or ""
            src_id = name_to_id.get(display)
            if not src_id:
                continue
            for syn in t.get("synonyms") or []:
                tgt_id = name_to_id.get(syn)
                if not tgt_id or tgt_id == src_id:
                    continue
                assoc_rows.append(
                    [
                        src_id,
                        tgt_id,
                        SHARED_TENANT,
                        "BusinessObject",
                        "BusinessObject",
                        "synonym",
                        "EXTRACTED",
                    ]
                )

        mutations: list[tuple[str, list[str], list[list]]] = []
        if bo_rows:
            mutations.append(
                (
                    "BusinessObjects",
                    [
                        "object_id",
                        "tenant_id",
                        "object_name",
                        "description",
                        "archimate_layer",
                        "source_doc_id",
                        "object_embedding",
                    ],
                    bo_rows,
                )
            )
        if assoc_rows:
            mutations.append(
                (
                    "Association",
                    [
                        "source_id",
                        "target_id",
                        "tenant_id",
                        "source_type",
                        "target_type",
                        "association_details",
                        "confidence",
                    ],
                    assoc_rows,
                )
            )
        return mutations, audit

    # -- public API --------------------------------------------------------

    def push(self, doc_id: str | None = None) -> dict[str, Any]:
        """Project KF BusinessObjects into KC Glossary Terms.

        Args:
            doc_id: optional source-doc filter; ``None`` means "all rows".

        Returns:
            Summary dict with ``terms_total`` and the built ``terms``
            payloads (useful for tests + audit).
        """
        rows = self._read_business_objects(doc_id)
        terms: list[dict[str, Any]] = []
        for r in rows:
            term_id = make_term_id(self.glossary_id, r["object_name"])
            payload = self._build_term_payload(
                term_id=term_id,
                display_name=r["object_name"],
                layer=r.get("archimate_layer") or "Business",
                description=r.get("description") or "",
                synonyms=r.get("synonyms") or [],
            )
            terms.append(payload)
            self._upsert_term(payload)

        summary = {
            "direction": "push",
            "doc_id": doc_id,
            "terms_total": len(terms),
            "terms": terms,
        }
        logger.info(
            "Glossary push done (doc=%s): %d terms", doc_id, len(terms)
        )
        return summary

    def pull(self) -> dict[str, Any]:
        """Pull KC GlossaryTerms into KF BusinessObjects + Associations."""
        from services.spanner_client import batch_write  # type: ignore

        terms = self._list_terms()
        mutations, audit = self._build_business_object_mutations(terms)
        if mutations:
            batch_write(mutations)

        summary = {
            "direction": "pull",
            "terms_total": len(terms),
            "business_objects": audit,
            "synonym_edges": sum(
                1 for m in mutations if m[0] == "Association" for _ in m[2]
            ),
        }
        logger.info(
            "Glossary pull done: %d terms -> %d BusinessObjects",
            len(terms),
            len(audit),
        )
        return summary

    def sync(
        self,
        direction: Literal["push", "pull", "both"] = "both",
        doc_id: str | None = None,
    ) -> dict[str, Any]:
        """Convenience wrapper around :meth:`push` and :meth:`pull`.

        Order on ``"both"``: push first, then pull. Push surfaces local
        BusinessObjects so a follow-up pull can merge any KC-side synonyms /
        descriptions added by glossary stewards.
        """
        out: dict[str, Any] = {"direction": direction}
        if direction in ("push", "both"):
            out["push"] = self.push(doc_id)
        if direction in ("pull", "both"):
            out["pull"] = self.pull()
        return out

    # -- upsert wrappers ---------------------------------------------------

    def _upsert_term(self, term: dict[str, Any]) -> None:
        """Create-or-update a GlossaryTerm. Idempotent via deterministic id.

        On AlreadyExists we merge synonyms (union) and overwrite the
        definition (last-write-wins), then update.
        """
        client = self.client
        parent = self._glossary_name()
        term_id = term["name"].rsplit("/", 1)[-1]

        create_fn = (
            getattr(client, "create_glossary_term", None)
            or getattr(client, "create_term", None)
        )
        update_fn = (
            getattr(client, "update_glossary_term", None)
            or getattr(client, "update_term", None)
        )
        get_fn = (
            getattr(client, "get_glossary_term", None)
            or getattr(client, "get_term", None)
        )
        if create_fn is None:
            raise RuntimeError(
                "Dataplex client lacks create_glossary_term / create_term"
            )

        try:
            create_fn(parent=parent, term_id=term_id, term=term)
        except Exception as exc:  # pragma: no cover - exercised via mock
            already_exists = (
                "already exists" in str(exc).lower()
                or exc.__class__.__name__ == "AlreadyExists"
            )
            if not already_exists or update_fn is None:
                raise
            # Merge synonyms (union) before update — never lose a synonym
            # that was added on the KC side by a glossary steward.
            if get_fn is not None:
                try:
                    existing = _term_to_dict(get_fn(name=term["name"]))
                    merged = sorted(
                        set(term.get("synonyms") or [])
                        | set(existing.get("synonyms") or [])
                    )
                    term = {**term, "synonyms": merged}
                except Exception:  # pragma: no cover - best effort
                    logger.debug(
                        "get_glossary_term failed for %s — updating without merge",
                        term_id,
                    )
            update_fn(term=term)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _term_to_dict(term: Any) -> dict[str, Any]:
    """Normalize a GlossaryTerm (dict OR proto-like) into a plain dict."""
    if isinstance(term, dict):
        return {
            "name": term.get("name", ""),
            "display_name": term.get("display_name", ""),
            "definition": term.get("definition", ""),
            "parent_category": term.get("parent_category", ""),
            "synonyms": list(term.get("synonyms") or []),
        }
    return {
        "name": getattr(term, "name", ""),
        "display_name": getattr(term, "display_name", ""),
        "definition": getattr(term, "definition", ""),
        "parent_category": getattr(term, "parent_category", ""),
        "synonyms": list(getattr(term, "synonyms", []) or []),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m kb_agent.services.glossary_sync",
        description=(
            "Bidirectional sync between KF BusinessObjects and a KC Glossary."
        ),
    )
    parser.add_argument(
        "--direction",
        choices=("push", "pull", "both"),
        default="both",
        help="Sync direction (default: both).",
    )
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Optional source doc filter (push only).",
    )
    args = parser.parse_args(argv)

    project = os.getenv("DATAPLEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        parser.error("DATAPLEX_PROJECT or GOOGLE_CLOUD_PROJECT must be set")

    sync = GlossarySync(
        project_id=project,
        location=os.getenv("KC_LOCATION", DEFAULT_LOCATION),
        glossary_id=os.getenv("KC_GLOSSARY_ID", DEFAULT_GLOSSARY_ID),
    )
    summary = sync.sync(direction=args.direction, doc_id=args.doc_id)
    push_n = summary.get("push", {}).get("terms_total", 0)
    pull_n = summary.get("pull", {}).get("terms_total", 0)
    print(
        f"Glossary sync direction={args.direction}: "
        f"pushed={push_n} pulled={pull_n}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
