# tests/test_retired_scripts.py
"""Guards against accidental removal of retirement tombstones."""
from pathlib import Path


def test_ingest_security_lifecycle_is_retired() -> None:
    path = Path("scripts/ingest_security_lifecycle.py")
    text = path.read_text(encoding="utf-8")

    assert "RETIRED SCRIPT" in text
    assert "DO NOT EXECUTE" in text
    assert "scripts/seed_security_lifecycle.py" in text
    assert "listed_from" in text
    assert "listed_to" in text
    assert "raise SystemExit" in text
