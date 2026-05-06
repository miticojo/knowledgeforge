"""Unit tests for services.git_ingester. Spanner and the network are mocked."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.git_ingester import GitIngester, _looks_like_sha


SAMPLE_PY = '''\
"""Tiny sample module."""
from os import path

class Thing:
    """A thing."""

    def do(self):
        return 1
'''


# ---------------------------------------------------------------- walk() tests

def test_walk_filters_includes_and_excludes(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test(): pass\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# hi\n")

    ig = GitIngester(
        repo_url="https://example.com/x.git",
        include=["**/*.py"],
        exclude=["tests/**"],
        writer=MagicMock(),
        embedder=MagicMock(return_value=[[0.0] * 768]),
    )
    found = sorted(str(p) for p in ig.walk(root=tmp_path))
    assert found == ["a.py", "b.py"]


def test_walk_default_includes_python_only(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "notes.md").write_text("# hi\n")
    ig = GitIngester(
        repo_url="https://example.com/x.git",
        writer=MagicMock(),
        embedder=MagicMock(return_value=[[0.0] * 768]),
    )
    found = sorted(str(p) for p in ig.walk(root=tmp_path))
    assert found == ["a.py"]


# --------------------------------------------------------------- clone() tests

def test_clone_uses_shallow_clone_with_branch(tmp_path):
    fake_repo = MagicMock()
    fake_repo.head.commit.hexsha = "deadbeef"

    with patch("git.Repo") as RepoCls:
        RepoCls.clone_from.return_value = fake_repo
        ig = GitIngester(
            repo_url="https://example.com/x.git",
            ref="main",
            workdir=tmp_path,
            writer=MagicMock(),
            embedder=MagicMock(return_value=[[0.0] * 768]),
        )
        path = ig.clone()

    RepoCls.clone_from.assert_called_once()
    args, kwargs = RepoCls.clone_from.call_args
    assert args[0] == "https://example.com/x.git"
    assert kwargs == {"depth": 1, "branch": "main"}
    assert ig._commit_sha == "deadbeef"
    assert path == tmp_path / "repo"


# ----------------------------------------------------- _looks_like_sha helper

def test_looks_like_sha_full_and_abbrev():
    assert _looks_like_sha("a" * 40)
    assert _looks_like_sha("deadbeef")          # 8 chars
    assert _looks_like_sha("abc1234")           # 7 chars
    assert _looks_like_sha("abcdef012345")      # 12 chars


def test_looks_like_sha_rejects_branches_and_tags():
    assert not _looks_like_sha("main")
    assert not _looks_like_sha("master")
    assert not _looks_like_sha("v1.2.3")
    assert not _looks_like_sha("release/foo")
    assert not _looks_like_sha("")
    assert not _looks_like_sha("ab")            # too short
    assert not _looks_like_sha("a" * 41)        # too long
    assert not _looks_like_sha("abcg123")       # non-hex


def test_clone_with_sha_ref_uses_fetch_and_checkout(tmp_path):
    """SHA refs must NOT be passed via --branch; fetch+checkout instead."""
    fake_repo = MagicMock()
    fake_repo.head.commit.hexsha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

    with patch("git.Repo") as RepoCls:
        RepoCls.clone_from.return_value = fake_repo
        ig = GitIngester(
            repo_url="https://example.com/x.git",
            ref=sha,
            workdir=tmp_path,
            writer=MagicMock(),
            embedder=MagicMock(return_value=[[0.0] * 768]),
        )
        ig.clone()

    _, kwargs = RepoCls.clone_from.call_args
    assert "branch" not in kwargs, "SHA ref must not be passed as --branch"
    assert kwargs == {"depth": 1}
    fake_repo.git.fetch.assert_called_once_with("--depth=1", "origin", sha)
    fake_repo.git.checkout.assert_called_once_with(sha)


def test_clone_with_short_sha_dispatches_to_fetch_path(tmp_path):
    fake_repo = MagicMock()
    fake_repo.head.commit.hexsha = "abc1234abc1234abc1234abc1234abc1234abcd"
    with patch("git.Repo") as RepoCls:
        RepoCls.clone_from.return_value = fake_repo
        ig = GitIngester(
            repo_url="https://example.com/x.git",
            ref="abc1234",
            workdir=tmp_path,
            writer=MagicMock(),
            embedder=MagicMock(return_value=[[0.0] * 768]),
        )
        ig.clone()
    _, kwargs = RepoCls.clone_from.call_args
    assert "branch" not in kwargs
    fake_repo.git.checkout.assert_called_once_with("abc1234")


def test_clone_with_tag_ref_uses_branch_path(tmp_path):
    fake_repo = MagicMock()
    fake_repo.head.commit.hexsha = "cafe"
    with patch("git.Repo") as RepoCls:
        RepoCls.clone_from.return_value = fake_repo
        ig = GitIngester(
            repo_url="https://example.com/x.git",
            ref="v1.2.3",
            workdir=tmp_path,
            writer=MagicMock(),
            embedder=MagicMock(return_value=[[0.0] * 768]),
        )
        ig.clone()
    _, kwargs = RepoCls.clone_from.call_args
    assert kwargs == {"depth": 1, "branch": "v1.2.3"}
    fake_repo.git.fetch.assert_not_called()
    fake_repo.git.checkout.assert_not_called()


def test_clone_without_ref_omits_branch(tmp_path):
    fake_repo = MagicMock()
    fake_repo.head.commit.hexsha = "cafef00d"
    with patch("git.Repo") as RepoCls:
        RepoCls.clone_from.return_value = fake_repo
        ig = GitIngester(
            repo_url="https://example.com/x.git",
            workdir=tmp_path,
            writer=MagicMock(),
            embedder=MagicMock(return_value=[[0.0] * 768]),
        )
        ig.clone()
    _, kwargs = RepoCls.clone_from.call_args
    assert kwargs == {"depth": 1}


# -------------------------------------------------------------- ingest() tests

def _prepare_clone(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a fake clone tree under tmp_path/repo and return the clone root."""
    clone = tmp_path / "repo"
    clone.mkdir()
    for rel, content in files.items():
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return clone


def test_ingest_dispatches_to_python_parser_and_writer(tmp_path):
    clone = _prepare_clone(tmp_path, {"mod.py": SAMPLE_PY})
    writer = MagicMock()
    embedder = MagicMock(return_value=[[0.1] * 768])

    ig = GitIngester(
        repo_url="https://example.com/x.git",
        workdir=tmp_path,
        writer=writer,
        embedder=embedder,
    )
    # Bypass the network clone — pretend it already happened.
    ig._clone_path = clone
    ig._commit_sha = "deadbeef"

    summary = ig.ingest()

    assert summary["files_processed"] == 1
    assert summary["files_skipped"] == 0
    assert summary["commit_sha"] == "deadbeef"
    assert summary["entities_total"] >= 3
    assert summary["edges_total"] >= 2
    assert summary["errors"] == []

    writer.assert_called_once()
    _args, kwargs = writer.call_args
    # graph_json passed as the first positional arg
    graph_json = _args[0]
    assert "extracted_nodes" in graph_json
    assert "extracted_edges" in graph_json
    assert kwargs["doc_id"] == "git:https://example.com/x.git@deadbeef:mod.py"
    assert kwargs["doc_title"] == "mod.py"
    assert kwargs["doc_summary"] == "Tiny sample module."
    assert kwargs["doc_embedding"] == [0.1] * 768

    # embedder called with module name + doc
    embedder.assert_called_once()
    embed_arg = embedder.call_args[0][0]
    assert embed_arg == [{"name": "mod\nTiny sample module."}]


def test_ingest_skips_unsupported_extensions(tmp_path):
    clone = _prepare_clone(
        tmp_path,
        {"mod.py": SAMPLE_PY, "notes.md": "# nope\n", "data.json": "{}"},
    )
    writer = MagicMock()
    ig = GitIngester(
        repo_url="https://example.com/x.git",
        include=["**/*"],            # include everything
        exclude=[],
        workdir=tmp_path,
        writer=writer,
        embedder=MagicMock(return_value=[[0.0] * 768]),
    )
    ig._clone_path = clone
    ig._commit_sha = "abc123"

    summary = ig.ingest()
    assert summary["files_processed"] == 1
    assert summary["files_skipped"] == 2
    assert writer.call_count == 1


def test_ingest_continues_on_syntax_error(tmp_path):
    clone = _prepare_clone(
        tmp_path,
        {"good.py": SAMPLE_PY, "bad.py": "def (((\n"},
    )
    writer = MagicMock()
    ig = GitIngester(
        repo_url="https://example.com/x.git",
        workdir=tmp_path,
        writer=writer,
        embedder=MagicMock(return_value=[[0.0] * 768]),
    )
    ig._clone_path = clone
    ig._commit_sha = "abc123"

    summary = ig.ingest()
    assert summary["files_processed"] == 1
    assert any("syntax error" in e for e in summary["errors"])


def test_parse_end_event_includes_entities_and_edges(tmp_path):
    """M3 Live Inspector contract: parse_end carries inspector-shaped lists."""
    clone = _prepare_clone(tmp_path, {"mod.py": SAMPLE_PY})
    events: list[tuple[str, dict]] = []

    ig = GitIngester(
        repo_url="https://example.com/x.git",
        workdir=tmp_path,
        writer=MagicMock(return_value={"resolution_map": {}}),
        embedder=MagicMock(return_value=[[0.0] * 768]),
        event_callback=lambda et, d: events.append((et, d)),
    )
    ig._clone_path = clone
    ig._commit_sha = "deadbeef"
    ig.ingest()

    parse_ends = [d for et, d in events if et == "parse_end"]
    assert len(parse_ends) == 1
    payload = parse_ends[0]
    assert "entities" in payload and isinstance(payload["entities"], list)
    assert "edges" in payload and isinstance(payload["edges"], list)
    assert payload["entities_added"] >= 3
    # Each entity has the documented inspector shape.
    sample = payload["entities"][0]
    assert {"id", "type", "name", "layer", "confidence"} <= set(sample.keys())
    # Edges reference entity IDs (string form).
    if payload["edges"]:
        e = payload["edges"][0]
        assert {"source", "target", "rel", "confidence"} <= set(e.keys())


def test_artifact_callback_receives_per_file_payload(tmp_path):
    """C: artifact callback fires once per processed file with the inspector shape."""
    clone = _prepare_clone(tmp_path, {"mod.py": SAMPLE_PY})
    captured: list[tuple[str, dict]] = []

    ig = GitIngester(
        repo_url="https://example.com/x.git",
        workdir=tmp_path,
        writer=MagicMock(return_value={"resolution_map": {}}),
        embedder=MagicMock(return_value=[[0.0] * 768]),
        artifact_callback=lambda fp, payload: captured.append((fp, payload)),
    )
    ig._clone_path = clone
    ig._commit_sha = "deadbeef"
    ig.ingest()

    assert len(captured) == 1
    fp, payload = captured[0]
    assert fp == "mod.py"
    assert payload["language"] == "python"
    assert payload["parser"] == "python-ast"
    assert payload["source"].startswith('"""Tiny sample module."""')
    assert isinstance(payload["parsed"], dict)
    assert "entities" in payload and "edges" in payload


def test_ingest_falls_back_to_zero_embedding_on_embedder_failure(tmp_path):
    clone = _prepare_clone(tmp_path, {"mod.py": SAMPLE_PY})
    writer = MagicMock()

    def boom(_):
        raise RuntimeError("network down")

    ig = GitIngester(
        repo_url="https://example.com/x.git",
        workdir=tmp_path,
        writer=writer,
        embedder=boom,
    )
    ig._clone_path = clone
    ig._commit_sha = "abc123"
    summary = ig.ingest()
    assert summary["files_processed"] == 1
    _, kwargs = writer.call_args
    assert kwargs["doc_embedding"] == [0.0] * 768
