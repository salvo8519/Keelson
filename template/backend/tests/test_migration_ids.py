"""Revision ids fit the column Alembic stores them in (Keelstone).

``alembic_version.version_num`` is ``VARCHAR(32)``: a longer id is accepted by every check that
reads the files and fails only when a database is upgraded past it. Checked without a database.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

VERSION_NUM_LENGTH = 32


def test_every_revision_id_fits_the_version_table() -> None:
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert revisions
    too_long = [r.revision for r in revisions if len(r.revision) > VERSION_NUM_LENGTH]
    assert not too_long, f"revision ids longer than {VERSION_NUM_LENGTH} characters: {too_long}"
