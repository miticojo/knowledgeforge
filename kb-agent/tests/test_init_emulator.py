"""Unit tests for kb-agent/scripts/init_emulator.py.

Mocks the Spanner client so no live emulator is required. Verifies:
  - DDL files are dispatched in production order:
        spanner_schema.sdl -> migrations/*.sql (alphabetical) -> add_tenant_id.ddl
  - Per-statement application: duplicate / already-exists errors are caught
    and the run continues; other errors are re-raised.
  - The CREATE MODEL / CREATE VECTOR INDEX filter still strips unsupported
    statements before they reach the database.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Load the script as a module (it lives under scripts/, not a package).
# ---------------------------------------------------------------------------
SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "init_emulator.py"
)
spec = importlib.util.spec_from_file_location("init_emulator", SCRIPT_PATH)
init_emulator = importlib.util.module_from_spec(spec)
sys.modules["init_emulator"] = init_emulator
spec.loader.exec_module(init_emulator)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# _split_ddl: filter behavior
# ---------------------------------------------------------------------------
class TestSplitDDL:
    def test_strips_line_comments_and_blank(self):
        ddl = """
        -- a comment
        CREATE TABLE Foo (id STRING(36)) PRIMARY KEY (id);

        -- another
        CREATE TABLE Bar (id STRING(36)) PRIMARY KEY (id);
        """
        stmts = init_emulator._split_ddl(ddl)
        assert len(stmts) == 2
        assert all("CREATE TABLE" in s for s in stmts)

    def test_filters_create_model(self):
        ddl = """
        CREATE TABLE Foo (id STRING(36)) PRIMARY KEY (id);
        CREATE MODEL EmbeddingModel INPUT (content STRING(MAX)) OUTPUT (embedding ARRAY<FLOAT32>) REMOTE OPTIONS (endpoint = '...');
        CREATE OR REPLACE MODEL OtherModel INPUT (x STRING(MAX)) OUTPUT (y ARRAY<FLOAT32>) REMOTE OPTIONS (endpoint = '...');
        """
        stmts = init_emulator._split_ddl(ddl)
        assert len(stmts) == 1
        assert "CREATE TABLE Foo" in stmts[0]
        assert not any("MODEL" in s.upper() for s in stmts)

    def test_filters_create_vector_index(self):
        ddl = """
        CREATE TABLE Foo (id STRING(36)) PRIMARY KEY (id);
        CREATE VECTOR INDEX Idx_Foo_Vec ON Foo(embedding) OPTIONS (distance_type = 'COSINE');
        CREATE OR REPLACE VECTOR INDEX Idx_Bar_Vec ON Bar(embedding);
        """
        stmts = init_emulator._split_ddl(ddl)
        assert len(stmts) == 1
        assert "CREATE TABLE Foo" in stmts[0]
        assert not any("VECTOR INDEX" in s.upper() for s in stmts)


# ---------------------------------------------------------------------------
# _is_duplicate_error
# ---------------------------------------------------------------------------
class TestIsDuplicateError:
    @pytest.mark.parametrize(
        "msg",
        [
            "Duplicate column name: tenant_id",
            "Table Documents already exists",
            "Column tenant_id already exists in table Documents",
            "Duplicate name 'Idx_Documents_TenantId'",
            "Index Idx_X is already present",
        ],
    )
    def test_recognises_duplicate(self, msg):
        assert init_emulator._is_duplicate_error(Exception(msg)) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "Syntax error near 'FOO'",
            "Unknown table Bar",
            "Permission denied",
            "Invalid type ARRAY<INT64>",
        ],
    )
    def test_rejects_real_error(self, msg):
        assert init_emulator._is_duplicate_error(Exception(msg)) is False


# ---------------------------------------------------------------------------
# _apply_statements: idempotent per-statement behavior
# ---------------------------------------------------------------------------
class _FakeOp:
    def result(self, timeout=None):  # noqa: ARG002
        return None


class _FakeDatabase:
    """Records each update_ddl call; raises on configured statements."""

    def __init__(self, raise_map: dict[int, Exception] | None = None):
        self.calls: list[list[str]] = []
        self.raise_map = raise_map or {}

    def update_ddl(self, stmts):
        idx = len(self.calls)
        self.calls.append(list(stmts))
        if idx in self.raise_map:
            raise self.raise_map[idx]
        return _FakeOp()


class TestApplyStatements:
    def test_all_apply(self):
        db = _FakeDatabase()
        stmts = ["CREATE TABLE A (id STRING(36)) PRIMARY KEY (id)",
                 "CREATE TABLE B (id STRING(36)) PRIMARY KEY (id)"]
        applied, skipped, errors = init_emulator._apply_statements(db, "x", stmts)
        assert (applied, skipped, errors) == (2, 0, 0)
        assert len(db.calls) == 2
        # one statement per call
        assert all(len(c) == 1 for c in db.calls)

    def test_duplicate_is_skipped_and_run_continues(self):
        db = _FakeDatabase(raise_map={1: Exception("Duplicate column name: tenant_id")})
        stmts = [
            "ALTER TABLE A ADD COLUMN x STRING(16)",
            "ALTER TABLE A ADD COLUMN tenant_id STRING(320)",  # duplicate
            "ALTER TABLE B ADD COLUMN x STRING(16)",
        ]
        applied, skipped, errors = init_emulator._apply_statements(db, "x", stmts)
        assert (applied, skipped, errors) == (2, 1, 0)
        assert len(db.calls) == 3  # all three attempted

    def test_real_error_is_reraised(self):
        db = _FakeDatabase(raise_map={0: Exception("Syntax error near 'FOO'")})
        with pytest.raises(Exception, match="Syntax error"):
            init_emulator._apply_statements(
                db, "x", ["CREATE TABLE FOO BAD"]
            )


# ---------------------------------------------------------------------------
# _collect_ddl_files: production order
# ---------------------------------------------------------------------------
class TestCollectDDLFiles:
    def test_order_schema_then_migrations_then_tenant(self, tmp_path: Path):
        (tmp_path / "spanner_schema.sdl").write_text("-- schema\n")
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        # write out-of-order to confirm sort
        (migrations / "002_b.sql").write_text("-- m2\n")
        (migrations / "001_a.sql").write_text("-- m1\n")
        (migrations / "010_c.sql").write_text("-- m10\n")
        (tmp_path / "add_tenant_id.ddl").write_text("-- tenant\n")

        files = init_emulator._collect_ddl_files(tmp_path)
        labels = [label for label, _ in files]
        assert labels == [
            "schema",
            "migration:001_a.sql",
            "migration:002_b.sql",
            "migration:010_c.sql",
            "tenant",
        ]

    def test_missing_optional_files_ok(self, tmp_path: Path):
        (tmp_path / "spanner_schema.sdl").write_text("-- schema\n")
        # no migrations dir, no tenant file
        files = init_emulator._collect_ddl_files(tmp_path)
        assert [l for l, _ in files] == ["schema"]

    def test_real_repo_layout_has_expected_order(self):
        """Sanity-check against the real database/ directory in the repo."""
        repo_db = SCRIPT_PATH.resolve().parents[2] / "database"
        files = init_emulator._collect_ddl_files(repo_db)
        labels = [l for l, _ in files]
        assert labels[0] == "schema"
        assert labels[-1] == "tenant"
        # everything in the middle is a migration, alphabetically sorted
        middle = labels[1:-1]
        assert all(l.startswith("migration:") for l in middle)
        assert middle == sorted(middle)


# ---------------------------------------------------------------------------
# main(): full dispatch order with mocked Spanner client
# ---------------------------------------------------------------------------
class TestMainDispatchOrder:
    def test_main_applies_files_in_order(self, tmp_path: Path, monkeypatch):
        # Build a fake database/ tree
        db_dir = tmp_path / "database"
        db_dir.mkdir()
        (db_dir / "spanner_schema.sdl").write_text(
            "CREATE TABLE Documents (id STRING(36)) PRIMARY KEY (id);\n"
            "CREATE MODEL EmbeddingModel INPUT (x STRING(MAX)) OUTPUT (y ARRAY<FLOAT32>) REMOTE OPTIONS (endpoint='x');\n"
        )
        migrations = db_dir / "migrations"
        migrations.mkdir()
        (migrations / "001_first.sql").write_text(
            "ALTER TABLE Documents ADD COLUMN confidence STRING(16);\n"
        )
        (migrations / "002_second.sql").write_text(
            "ALTER TABLE Documents ADD COLUMN extra STRING(16);\n"
        )
        (db_dir / "add_tenant_id.ddl").write_text(
            "ALTER TABLE Documents ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');\n"
        )

        # Make _collect_ddl_files & main pull from our tmp dir.
        # main() resolves database/ relative to the script path, so monkeypatch Path resolution.
        monkeypatch.setattr(
            init_emulator, "_collect_ddl_files",
            lambda _d: init_emulator.__wrapped_collect__(db_dir)
            if False else _real_collect(db_dir),
        )

        # Simpler: replace with direct call
        def fake_collect(_d):
            return [
                ("schema", db_dir / "spanner_schema.sdl"),
                ("migration:001_first.sql", migrations / "001_first.sql"),
                ("migration:002_second.sql", migrations / "002_second.sql"),
                ("tenant", db_dir / "add_tenant_id.ddl"),
            ]
        monkeypatch.setattr(init_emulator, "_collect_ddl_files", fake_collect)

        # Patch schema_path lookup: main() checks `database_dir / "spanner_schema.sdl"` exists
        # — our fake dir already contains it, but main computes database_dir from the script
        # path. Patch Path.resolve via a shim: monkeypatch the module-level Path used in main.
        monkeypatch.setattr(
            init_emulator, "Path", _PathShim(real_db_dir=db_dir),
        )

        # Mock the Spanner client.
        fake_db = _FakeDatabase()
        fake_instance = mock.MagicMock()
        fake_instance.exists.return_value = True
        fake_instance.database.return_value = fake_db
        fake_db_obj_exists = mock.MagicMock()
        # database.exists() should return True so main() skips create
        fake_db.exists = mock.MagicMock(return_value=True)  # type: ignore[attr-defined]

        fake_client = mock.MagicMock()
        fake_client.instance.return_value = fake_instance

        fake_spanner = mock.MagicMock()
        fake_spanner.Client.return_value = fake_client
        fake_creds_mod = mock.MagicMock()

        with mock.patch.dict(sys.modules, {
            "google.cloud": mock.MagicMock(spanner=fake_spanner),
            "google.cloud.spanner": fake_spanner,
            "google.auth": mock.MagicMock(),
            "google.auth.credentials": fake_creds_mod,
        }):
            rc = init_emulator.main()

        assert rc == 0

        # Flatten all DDL statements seen by the fake DB, in order.
        flat = [c[0] for c in fake_db.calls]
        # 1 from schema (MODEL filtered) + 1 + 1 + 1 = 4 statements
        assert len(flat) == 4
        assert "CREATE TABLE Documents" in flat[0]
        assert "confidence" in flat[1]
        assert "extra" in flat[2]
        assert "tenant_id" in flat[3]

    def test_main_continues_on_duplicate_errors(self, tmp_path: Path, monkeypatch):
        db_dir = tmp_path / "database"
        db_dir.mkdir()
        (db_dir / "spanner_schema.sdl").write_text(
            "CREATE TABLE Documents (id STRING(36)) PRIMARY KEY (id);\n"
        )
        (db_dir / "add_tenant_id.ddl").write_text(
            "ALTER TABLE Documents ADD COLUMN tenant_id STRING(320) NOT NULL DEFAULT ('__shared__');\n"
        )

        def fake_collect(_d):
            return [
                ("schema", db_dir / "spanner_schema.sdl"),
                ("tenant", db_dir / "add_tenant_id.ddl"),
            ]
        monkeypatch.setattr(init_emulator, "_collect_ddl_files", fake_collect)
        monkeypatch.setattr(init_emulator, "Path", _PathShim(real_db_dir=db_dir))

        # Both statements raise duplicate errors — main should still return 0.
        fake_db = _FakeDatabase(raise_map={
            0: Exception("Table Documents already exists"),
            1: Exception("Duplicate column name: tenant_id"),
        })
        fake_db.exists = mock.MagicMock(return_value=True)  # type: ignore[attr-defined]
        fake_instance = mock.MagicMock()
        fake_instance.exists.return_value = True
        fake_instance.database.return_value = fake_db
        fake_client = mock.MagicMock()
        fake_client.instance.return_value = fake_instance
        fake_spanner = mock.MagicMock()
        fake_spanner.Client.return_value = fake_client

        with mock.patch.dict(sys.modules, {
            "google.cloud": mock.MagicMock(spanner=fake_spanner),
            "google.cloud.spanner": fake_spanner,
            "google.auth": mock.MagicMock(),
            "google.auth.credentials": mock.MagicMock(),
        }):
            rc = init_emulator.main()
        assert rc == 0
        # Both statements were attempted
        assert len(fake_db.calls) == 2


# ---------------------------------------------------------------------------
# Helpers for main() patching
# ---------------------------------------------------------------------------
def _real_collect(db_dir: Path):
    return init_emulator._collect_ddl_files(db_dir)


class _PathShim:
    """Stand-in for pathlib.Path in init_emulator namespace.

    Only used so that `Path(__file__).resolve().parents[2] / "database"` inside
    main() routes to our test temp dir. Falls back to real Path for any other
    constructor arg.
    """

    def __init__(self, real_db_dir: Path):
        self._real_db_dir = real_db_dir

    def __call__(self, arg):
        from pathlib import Path as _RealPath

        # When main() does Path(__file__), return a shim whose
        # .resolve().parents[2] / "database" resolves to our temp dir.
        class _Shim:
            def __init__(self, real_db_dir):
                self._real_db_dir = real_db_dir

            def resolve(self):
                return self

            @property
            def parents(self):
                # parents[2] / "database" must equal real_db_dir
                # so parents[2] should be real_db_dir.parent
                shim = self

                class _Parents:
                    def __getitem__(self_inner, idx):
                        if idx == 2:
                            return shim._real_db_dir.parent
                        return _RealPath("/")
                return _Parents()

        return _Shim(self._real_db_dir)
