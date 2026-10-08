"""Version, Build, Copyright und Lizenzhinweise."""

from pathlib import Path

from s7py import COPYRIGHT, LICENSE_NAME, __version__
from s7py.about import Build, build_info, license_text, system_info, third_party
from s7py import help as manual


def test_version_matches_pyproject() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in text
    assert __version__ == "0.9.0"
    assert "MIT" in LICENSE_NAME
    assert "2026" in COPYRIGHT


def test_build_and_system_info() -> None:
    build = build_info()
    if (Path(".git")).exists():
        assert len(build.commit) >= 7
        assert build.date[:2] == "20"
    assert str(Build("", "")) == "unbekannt"
    assert "vom" in str(Build("abc1234", "2026-10-08", True))
    assert "lokalen" in str(Build("abc1234", "2026-10-08", True))
    text = system_info()
    assert text.startswith(f"s7py {__version__}")
    assert "Build:" in text
    assert third_party()
    assert "MIT License" in license_text()


def test_help_documents_exist() -> None:
    for name, title in manual.DOCUMENTS.items():
        source = manual.source(name)
        assert title.split()[0].lower() in source.lower() or "s7py" in source.lower()
        heads = manual.headings(source)
        assert heads and heads[0][0] == 1
