"""Migration tests — verify Alembic upgrade/downgrade cycle.

These tests ensure that:
1. All migrations can be applied (upgrade head)
2. All migrations can be rolled back (downgrade base)
3. The upgrade/downgrade cycle is idempotent
"""

import subprocess
import sys

import pytest


def _db_available() -> bool:
    """Return True if the database answers a connection.

    Checked directly rather than through `alembic current`: that also fails on
    a broken migration chain, which would then skip these tests as "no
    database" instead of failing them.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError

    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL_SYNC, connect_args={"connect_timeout": 5})
    try:
        with engine.connect():
            return True
    except OperationalError:
        return False
    finally:
        engine.dispose()


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="No live database available — skipping migration tests",
)


class TestMigrations:
    """Test Alembic migration integrity."""

    def test_upgrade_head(self):
        """Test that all migrations can be applied successfully."""
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert result.returncode == 0, f"Migration upgrade failed:\n{result.stderr}"

    def test_downgrade_base(self):
        """Test that all migrations can be rolled back."""
        # First upgrade to head
        up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert up.returncode == 0, f"Migration upgrade failed:\n{up.stderr}"

        # Then downgrade to base
        down = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert down.returncode == 0, f"Migration downgrade failed:\n{down.stderr}"

    def test_upgrade_downgrade_cycle(self):
        """Test that upgrade → downgrade → upgrade produces consistent state."""
        for cmd in ["upgrade head", "downgrade base", "upgrade head"]:
            action, target = cmd.split()
            result = subprocess.run(
                [sys.executable, "-m", "alembic", action, target],
                capture_output=True,
                text=True,
                cwd=".",
            )
            assert result.returncode == 0, f"alembic {cmd} failed:\n{result.stderr}"

    def test_current_matches_head(self):
        """Test that current migration revision matches head after upgrade."""
        # Upgrade to head first
        up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert up.returncode == 0, f"Migration upgrade failed:\n{up.stderr}"

        # Check if there are any migration revisions
        heads = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert heads.returncode == 0

        if not heads.stdout.strip():
            pytest.skip("No migration revisions found — nothing to verify")

        # Check current
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert result.returncode == 0
        assert "(head)" in result.stdout, (
            f"Current revision is not at head:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_the_migrated_users_table_guards_its_sessions(self):
        """Keelstone: the migrations, not only the models, give users the confirmed-address
        column and the trigger that keeps the session version from decreasing (k0009, k0010)."""
        from sqlalchemy import create_engine, text

        from app.core.config import settings
        from app.db.tenancy import POLICY_PREFIX

        up = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True, cwd="."
        )
        assert up.returncode == 0, f"Migration upgrade failed:\n{up.stderr}"
        engine = create_engine(settings.DATABASE_URL_SYNC, connect_args={"connect_timeout": 5})
        try:
            with engine.connect() as connection:
                column = connection.scalar(
                    text(
                        "SELECT column_default FROM information_schema.columns "
                        "WHERE table_name = 'users' AND column_name = 'email_verified'"
                    )
                )
                trigger = connection.scalar(
                    text("SELECT tgname FROM pg_trigger WHERE tgname = :name AND NOT tgisinternal"),
                    {"name": f"{POLICY_PREFIX}token_epoch_never_decreases"},
                )
        finally:
            engine.dispose()
        assert column == "false"
        assert trigger == f"{POLICY_PREFIX}token_epoch_never_decreases"
