"""Knowledge Catalog (Dataplex) exporter for the KnowledgeForge graph.

Milestone B: opt-in projection of the Spanner KF graph (DataObject + edges) into
Google Knowledge Catalog (Dataplex Catalog) as Entry / Aspect / EntryLink.

Mapping (KF -> KC):
    DataObject                                 -> Entry  (entry_type "kf-legacy-data-object")
    Access (App -> Data)                       -> EntryLink (type "kf-accesses")
    Realization (Component -> DataObject)      -> EntryLink (type "kf-realizes")
    BusinessObject <-> DataObject (Realization)-> EntryLink (type "definition")
    Edge confidence + source_doc_id + page     -> Aspect "kf-extraction-provenance"
                                                  attached to source/target Entries

Idempotency:
    entry_id = uuid.uuid5(NAMESPACE_DNS, f"{doc_id}:{entity_name}")
    All writes use upsert (create-or-update) semantics so the exporter is safe to
    re-run for the same doc_id.

Gating:
    Disabled by default. Set KC_SYNC_ENABLED=true to allow exports. Calling
    `export_doc` while disabled raises `KCExportDisabled` to make the no-op
    explicit at the call site.

CLI:
    python -m services.kc_exporter --doc-id <id>
    Required env: DATAPLEX_PROJECT (or GOOGLE_CLOUD_PROJECT), KC_SYNC_ENABLED=true
    Optional env: KC_LOCATION (default europe-west1),
                  KC_ENTRY_GROUP_ID (default kf-import)
"""
from __future__ import annotations

import argparse
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTRY_TYPE_DATA_OBJECT = "kf-legacy-data-object"
ENTRY_TYPE_BUSINESS_OBJECT = "kf-business-object"

ENTRY_LINK_TYPE_ACCESSES = "kf-accesses"
ENTRY_LINK_TYPE_REALIZES = "kf-realizes"
ENTRY_LINK_TYPE_DEFINITION = "definition"

ASPECT_TYPE_PROVENANCE = "kf-extraction-provenance"


class KCExportDisabled(RuntimeError):
    """Raised when export_doc is called but KC_SYNC_ENABLED is not true."""


def _is_enabled() -> bool:
    return os.getenv("KC_SYNC_ENABLED", "false").lower() in ("1", "true", "yes")


def make_entry_id(doc_id: str, entity_name: str) -> str:
    """Deterministic UUID v5 used as KC entry_id. Stable across runs => upserts."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{entity_name}"))


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


class KCExporter:
    """Project the KF Spanner graph for a given doc into Knowledge Catalog.

    Args:
        project_id: GCP project that owns the Dataplex catalog.
        location: KC location (default europe-west1).
        entry_group_id: target entry group; created out-of-band by Terraform.
        dataplex_client: optional pre-built CatalogServiceClient — primarily for
            tests. When None, a real client is constructed lazily.
    """

    def __init__(
        self,
        project_id: str,
        location: str = "europe-west1",
        entry_group_id: str = "kf-import",
        dataplex_client: Any = None,
    ):
        self.project_id = project_id
        self.location = location
        self.entry_group_id = entry_group_id
        self._client = dataplex_client
        self._stats: dict[str, int] = {}

    # -- client lazy build -------------------------------------------------

    @property
    def client(self) -> Any:
        if self._client is None:
            # Imported lazily so the module can be imported in environments
            # without google-cloud-dataplex installed (tests use importorskip).
            from google.cloud import dataplex_v1  # type: ignore

            self._client = dataplex_v1.CatalogServiceClient()
        return self._client

    # -- name helpers ------------------------------------------------------

    def _entry_group_name(self) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}"
            f"/entryGroups/{self.entry_group_id}"
        )

    def _entry_name(self, entry_id: str) -> str:
        return f"{self._entry_group_name()}/entries/{entry_id}"

    # -- payload builders --------------------------------------------------

    def _build_entry(
        self,
        entry_id: str,
        entity_type: str,
        entity_name: str,
        entry_type: str,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        """Build an Entry payload (dict, easy to assert in tests)."""
        return {
            "name": self._entry_name(entry_id),
            "entry_type": (
                f"projects/{self.project_id}/locations/{self.location}"
                f"/entryTypes/{entry_type}"
            ),
            "entry_source": {
                "resource": entity_name,
                "system": "knowledgeforge",
                "display_name": entity_name,
            },
            "aspects": {
                ASPECT_TYPE_PROVENANCE: self._build_provenance_aspect(provenance),
            },
            "_kf": {  # internal hint for tests / debugging — not sent to GCP
                "entity_type": entity_type,
                "entity_name": entity_name,
            },
        }

    def _build_provenance_aspect(self, provenance: dict[str, Any]) -> dict[str, Any]:
        """Aspect payload carrying KF extraction metadata.

        Schema (informal, attached as Aspect "kf-extraction-provenance"):
            confidence:    EXTRACTED | INFERRED | AMBIGUOUS
            source_doc_id: UUID of the document the entity/edge was extracted from
            page:          optional page number (int) within the source doc
        """
        data = {
            "confidence": provenance.get("confidence", "EXTRACTED"),
            "source_doc_id": provenance.get("source_doc_id", ""),
        }
        if provenance.get("page") is not None:
            data["page"] = provenance["page"]
        return {
            "aspect_type": (
                f"projects/{self.project_id}/locations/{self.location}"
                f"/aspectTypes/{ASPECT_TYPE_PROVENANCE}"
            ),
            "data": data,
        }

    def _build_entry_link(
        self,
        link_type: str,
        source_entry_id: str,
        target_entry_id: str,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        # Deterministic link id so reruns upsert the same EntryLink.
        link_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{link_type}:{source_entry_id}:{target_entry_id}",
            )
        )
        return {
            "name": (
                f"{self._entry_group_name()}/entryLinks/{link_id}"
            ),
            "entry_link_type": (
                f"projects/{self.project_id}/locations/{self.location}"
                f"/entryLinkTypes/{link_type}"
            ),
            "entry_references": [
                {"name": self._entry_name(source_entry_id), "type": "SOURCE"},
                {"name": self._entry_name(target_entry_id), "type": "TARGET"},
            ],
            "_kf_provenance": {
                "confidence": provenance.get("confidence", "EXTRACTED"),
                "source_doc_id": provenance.get("source_doc_id", ""),
            },
        }

    # -- spanner reads -----------------------------------------------------

    def _read_graph(self, doc_id: str) -> dict[str, list[dict]]:
        """Read DataObjects + relevant edges for `doc_id` from Spanner.

        Returns a dict with keys: data_objects, business_objects, accesses,
        realizations. Each is a list of plain dicts.
        """
        # Imported lazily so unit tests can patch this method directly without
        # needing Spanner configured.
        from services.spanner_client import run_query  # type: ignore

        data_objects = run_query(
            "SELECT model_id, model_name, source_doc_id "
            "FROM DataObjects WHERE source_doc_id = @doc_id",
            params={"doc_id": doc_id},
        )
        business_objects = run_query(
            "SELECT object_id, object_name, source_doc_id "
            "FROM BusinessObjects WHERE source_doc_id = @doc_id",
            params={"doc_id": doc_id},
        )
        accesses = run_query(
            "SELECT source_id, target_id, source_type, target_type, "
            "       access_type, confidence "
            "FROM Access WHERE source_doc_id = @doc_id",
            params={"doc_id": doc_id},
        )
        realizations = run_query(
            "SELECT source_id, target_id, source_type, target_type, "
            "       details, confidence "
            "FROM Realization WHERE source_doc_id = @doc_id",
            params={"doc_id": doc_id},
        )
        return {
            "data_objects": data_objects,
            "business_objects": business_objects,
            "accesses": accesses,
            "realizations": realizations,
        }

    # -- main entry point --------------------------------------------------

    def export_doc(self, doc_id: str) -> dict[str, Any]:
        """Project the graph for `doc_id` into Knowledge Catalog.

        Returns a summary dict with counts plus the lists of payloads that were
        upserted (useful for tests + audit logs).
        """
        if not _is_enabled():
            raise KCExportDisabled(
                "KC export is disabled. Set KC_SYNC_ENABLED=true to opt in."
            )

        graph = self._read_graph(doc_id)

        entries: list[dict[str, Any]] = []
        entry_links: list[dict[str, Any]] = []
        # entity (type, name) -> entry_id, used to resolve edge endpoints
        id_lookup: dict[tuple[str, str], str] = {}

        # --- DataObjects -> Entry ---
        for row in graph["data_objects"]:
            name = row["model_name"]
            entry_id = make_entry_id(doc_id, name)
            id_lookup[("DataObject", name)] = entry_id
            entries.append(
                self._build_entry(
                    entry_id=entry_id,
                    entity_type="DataObject",
                    entity_name=name,
                    entry_type=ENTRY_TYPE_DATA_OBJECT,
                    provenance={
                        "confidence": "EXTRACTED",
                        "source_doc_id": row.get("source_doc_id") or doc_id,
                    },
                )
            )

        # --- BusinessObjects -> Entry (so we can link them) ---
        for row in graph["business_objects"]:
            name = row["object_name"]
            entry_id = make_entry_id(doc_id, name)
            id_lookup[("BusinessObject", name)] = entry_id
            entries.append(
                self._build_entry(
                    entry_id=entry_id,
                    entity_type="BusinessObject",
                    entity_name=name,
                    entry_type=ENTRY_TYPE_BUSINESS_OBJECT,
                    provenance={
                        "confidence": "EXTRACTED",
                        "source_doc_id": row.get("source_doc_id") or doc_id,
                    },
                )
            )

        # --- Edges. Endpoints are stored in Spanner as entity UUIDs; the
        # exporter operates on (type, name) tuples. To avoid an extra join,
        # callers (or _read_graph in production) may resolve names ahead of
        # time and stash them in `source_name` / `target_name`. When absent we
        # fall back to the raw id, which still produces a deterministic — and
        # idempotent — KC entry_id.

        def _endpoint_entry_id(row: dict[str, Any], side: str, default_type: str) -> str:
            type_ = row.get(f"{side}_type") or default_type
            name = row.get(f"{side}_name") or row.get(f"{side}_id")
            entry_id = id_lookup.get((type_, name))
            if entry_id is None:
                entry_id = make_entry_id(doc_id, name)
                id_lookup[(type_, name)] = entry_id
            return entry_id

        # Access (App -> Data) -> EntryLink "kf-accesses"
        for edge in graph["accesses"]:
            src_id = _endpoint_entry_id(edge, "source", "ApplicationComponent")
            tgt_id = _endpoint_entry_id(edge, "target", "DataObject")
            entry_links.append(
                self._build_entry_link(
                    link_type=ENTRY_LINK_TYPE_ACCESSES,
                    source_entry_id=src_id,
                    target_entry_id=tgt_id,
                    provenance={
                        "confidence": edge.get("confidence", "EXTRACTED"),
                        "source_doc_id": doc_id,
                    },
                )
            )

        # Realization. Two flavours:
        #   Component -> DataObject  => kf-realizes
        #   DataObject -> BusinessObject => definition (only when BO exists)
        for edge in graph["realizations"]:
            src_type = edge.get("source_type")
            tgt_type = edge.get("target_type")
            src_id = _endpoint_entry_id(edge, "source", src_type or "ApplicationComponent")
            tgt_id = _endpoint_entry_id(edge, "target", tgt_type or "DataObject")

            if src_type == "DataObject" and tgt_type == "BusinessObject":
                # Only emit `definition` when the BusinessObject was actually
                # exported as an Entry — otherwise the link dangles.
                bo_name = edge.get("target_name")
                if bo_name and ("BusinessObject", bo_name) in id_lookup:
                    entry_links.append(
                        self._build_entry_link(
                            link_type=ENTRY_LINK_TYPE_DEFINITION,
                            source_entry_id=src_id,
                            target_entry_id=tgt_id,
                            provenance={
                                "confidence": edge.get("confidence", "EXTRACTED"),
                                "source_doc_id": doc_id,
                            },
                        )
                    )
            else:
                entry_links.append(
                    self._build_entry_link(
                        link_type=ENTRY_LINK_TYPE_REALIZES,
                        source_entry_id=src_id,
                        target_entry_id=tgt_id,
                        provenance={
                            "confidence": edge.get("confidence", "EXTRACTED"),
                            "source_doc_id": doc_id,
                        },
                    )
                )

        # --- Upsert against the Catalog API ---
        for entry in entries:
            self._upsert_entry(entry)
        for link in entry_links:
            self._upsert_entry_link(link)

        summary = {
            "doc_id": doc_id,
            "entries_total": len(entries),
            "entry_links_total": len(entry_links),
            "entries": entries,
            "entry_links": entry_links,
        }
        logger.info(
            "KC export done for doc=%s: %d entries, %d links",
            doc_id,
            len(entries),
            len(entry_links),
        )
        return summary

    # -- upsert wrappers ---------------------------------------------------

    def _upsert_entry(self, entry: dict[str, Any]) -> None:
        """Create-or-update an Entry. Idempotent thanks to deterministic name."""
        client = self.client
        parent = self._entry_group_name()
        entry_id = entry["name"].rsplit("/", 1)[-1]
        try:
            client.create_entry(parent=parent, entry_id=entry_id, entry=entry)
        except Exception as exc:  # pragma: no cover - exercised via tests w/ mock
            # AlreadyExists -> fall back to update. We catch broadly because the
            # exact exception type depends on which transport (gRPC vs REST) is
            # in use; the mock used in tests raises a simple Exception subclass.
            if "already exists" in str(exc).lower() or exc.__class__.__name__ == "AlreadyExists":
                client.update_entry(entry=entry)
            else:
                raise

    def _upsert_entry_link(self, link: dict[str, Any]) -> None:
        client = self.client
        parent = self._entry_group_name()
        link_id = link["name"].rsplit("/", 1)[-1]
        try:
            client.create_entry_link(
                parent=parent, entry_link_id=link_id, entry_link=link
            )
        except Exception as exc:  # pragma: no cover - exercised via mock
            if (
                "already exists" in str(exc).lower()
                or exc.__class__.__name__ == "AlreadyExists"
            ):
                # EntryLinks in Dataplex are immutable; re-create after delete
                # would be destructive, so on AlreadyExists we treat the export
                # as a no-op for that link (its content is fully derived from
                # the deterministic id, so the existing link is equivalent).
                logger.debug("EntryLink %s already exists — skipping", link_id)
            else:
                raise


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m services.kc_exporter",
        description="Export a KnowledgeForge document graph to Knowledge Catalog.",
    )
    parser.add_argument("--doc-id", required=True, help="Source document UUID")
    args = parser.parse_args(argv)

    project = os.getenv("DATAPLEX_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        parser.error("DATAPLEX_PROJECT or GOOGLE_CLOUD_PROJECT must be set")

    exporter = KCExporter(
        project_id=project,
        location=os.getenv("KC_LOCATION", "europe-west1"),
        entry_group_id=os.getenv("KC_ENTRY_GROUP_ID", "kf-import"),
    )
    try:
        summary = exporter.export_doc(args.doc_id)
    except KCExportDisabled as exc:
        print(str(exc))
        return 2
    print(
        f"Exported doc {summary['doc_id']}: "
        f"{summary['entries_total']} entries, {summary['entry_links_total']} links"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
