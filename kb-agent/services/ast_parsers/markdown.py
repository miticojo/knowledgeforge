"""Markdown 'parser' that uses Gemini Controlled Generation to extract
ArchiMate entities/relationships from prose docs.

Unlike the language AST parsers (which return ParsedFile and rely on
ast_to_archimate.to_graph), this module returns a graph_json dict directly
in the same shape that `to_graph` produces: ``{"extracted_nodes": [...],
"extracted_edges": [...]}``.

The git_ingester detects markdown files and dispatches here, bypassing the
ParsedFile -> to_graph step.

Falls back to empty graph (text-only chunks) on any extraction error so
ingestion never fails hard on transient Gemini issues.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_ENTITY_TYPES = Literal[
    "ApplicationComponent", "DataObject", "BusinessProcess", "Requirement",
    "Node", "SystemSoftware", "TechnologyService", "BusinessActor",
    "BusinessRole", "BusinessService", "BusinessFunction", "BusinessObject",
    "ApplicationService", "ApplicationInterface", "Artifact", "Device",
    "CommunicationNetwork", "Contract", "Goal", "Constraint", "Stakeholder",
    "Capability",
]

_RELATIONSHIP_TYPES = Literal[
    "Composition", "Aggregation", "Assignment", "Realization", "Serving",
    "Access", "Influence", "Association", "Triggering", "Flow", "Specialization",
]

_CONFIDENCE_LEVELS = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]


class _ExtractedNode(BaseModel):
    entity_type: _ENTITY_TYPES
    entity_name: str


class _ExtractedEdge(BaseModel):
    source_type: _ENTITY_TYPES
    source_name: str
    relationship_type: _RELATIONSHIP_TYPES
    target_type: _ENTITY_TYPES
    target_name: str
    qualifier: Optional[str] = None
    confidence: _CONFIDENCE_LEVELS = "EXTRACTED"


class _GraphExtraction(BaseModel):
    nodes: list[_ExtractedNode]
    edges: list[_ExtractedEdge]


_PROMPT = """Extract ALL entities and relationships from this document following the ArchiMate 3.2 ontology.

ENTITY TYPES (22): ApplicationComponent, DataObject, BusinessProcess, Requirement, Node, SystemSoftware, TechnologyService, BusinessActor, BusinessRole, BusinessService, BusinessFunction, BusinessObject, ApplicationService, ApplicationInterface, Artifact, Device, CommunicationNetwork, Contract, Goal, Constraint, Stakeholder, Capability.

RELATIONSHIP TYPES (11): Composition, Aggregation, Assignment, Realization, Serving, Access, Influence, Association, Triggering, Flow, Specialization.

DIRECTION RULES:
- Assignment: Active Structure -> Behavior (Actor -> Process, Node -> Artifact)
- Realization: Concrete -> Abstract (App -> Requirement, Artifact -> App)
- Serving: Provider -> Consumer (TechService -> App, App -> BusinessProcess)
- Access: Behavior -> Data (qualifier: Read, Write, ReadWrite)
- Composition/Aggregation: Whole -> Part
- Influence: any -> Motivation element (qualifier: +, -, ++, --)
- Triggering/Flow: Source -> Destination

CONFIDENCE: EXTRACTED if explicit, INFERRED if deduced from context, AMBIGUOUS if uncertain.

Be exhaustive — extract every named actor, role, process, capability, goal, application, service, data object, node, technology mentioned, and every relationship between them.

DOCUMENT:
{document_text}"""


def _extract_title(text: str) -> str:
    m = re.search(r"^\s*#\s+(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _extract_first_paragraph(text: str) -> str:
    # strip leading H1 then take first non-empty paragraph
    body = re.sub(r"^\s*#\s+.+$", "", text, count=1, flags=re.MULTILINE)
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if para and not para.startswith("#"):
            return para[:1000]
    return ""


def parse(text: str, file_path: str) -> dict:
    """Extract ArchiMate graph from a markdown document via Gemini.

    Returns a dict with keys:
      - extracted_nodes: list[str]   (graph_json shape)
      - extracted_edges: list[str]
      - title: str                   (first H1, or filename)
      - summary: str                 (first paragraph)
    On extraction failure returns empty nodes/edges so ingestion can still
    write text-only chunks for retrieval.
    """
    title = _extract_title(text) or file_path
    summary = _extract_first_paragraph(text)

    # Cap input — these docs are small but be safe.
    truncated = text[:20000]

    try:
        from google import genai
        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=_PROMPT.format(document_text=truncated),
            config=genai.types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=_GraphExtraction,
                thinking_config=genai.types.ThinkingConfig(thinking_budget=0),
            ),
        )
        try:
            from services.cost_tracker import get_tracker
            tracker = get_tracker()
            if tracker:
                tracker.track_generate(response, model="gemini-2.5-flash")
        except Exception:
            pass

        data = json.loads(response.text)
        extraction = _GraphExtraction(**data)

        nodes = [f"{n.entity_type}:{n.entity_name}" for n in extraction.nodes]
        edges = []
        for e in extraction.edges:
            bracket_parts = []
            if e.qualifier:
                bracket_parts.append(e.qualifier)
            bracket_parts.append(e.confidence or "EXTRACTED")
            edge_str = (
                f"{e.source_type}:{e.source_name}"
                f"->{e.relationship_type}[{','.join(bracket_parts)}]"
                f"->{e.target_type}:{e.target_name}"
            )
            edges.append(edge_str)

        logger.info(
            "markdown extraction for %s: %d nodes, %d edges",
            file_path, len(nodes), len(edges),
        )
        return {
            "extracted_nodes": nodes,
            "extracted_edges": edges,
            "title": title,
            "summary": summary,
        }
    except Exception as e:
        logger.warning(
            "markdown Gemini extraction failed for %s (%s); ingesting as plain text",
            file_path, e,
        )
        return {
            "extracted_nodes": [],
            "extracted_edges": [],
            "title": title,
            "summary": summary,
        }
