"""Setup script for the KnowledgeForge kb-agent package.

Historically the repo only used `requirements.txt`. The `setup.py` exists so
that optional integrations (e.g. Knowledge Catalog export — Milestone B) can be
installed via extras:

    pip install -e .          # core
    pip install -e ".[kc]"    # core + Dataplex Knowledge Catalog export
"""
from pathlib import Path

from setuptools import find_packages, setup


_HERE = Path(__file__).parent


def _read_requirements() -> list[str]:
    req = _HERE / "requirements.txt"
    if not req.exists():
        return []
    lines = []
    for raw in req.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


setup(
    name="knowledgeforge",
    version="0.1.0",
    description="KnowledgeForge agentic knowledge base (kb-agent).",
    packages=find_packages(exclude=("tests", "tests.*")),
    install_requires=_read_requirements(),
    extras_require={
        # Optional: required for the Knowledge Catalog exporter
        # (services/kc_exporter.py). Listed as an extra so deployments that do
        # not opt into KC sync don't have to pull the Dataplex SDK.
        # Milestone B (exporter) needs google-cloud-dataplex.
        # Milestone C (reverse importer) additionally consumes a Pub/Sub
        # change-feed via google-cloud-pubsub.
        "kc": [
            "google-cloud-dataplex>=2.0",
            "google-cloud-pubsub>=2.0",
        ],
    },
    python_requires=">=3.10",
)
