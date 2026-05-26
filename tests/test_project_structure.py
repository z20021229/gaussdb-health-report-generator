from importlib import import_module
from pathlib import Path


def test_src_modules_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    expected = [
        root / "src" / "__init__.py",
        root / "src" / "archive_extractor.py",
        root / "src" / "inspection_parser.py",
        root / "src" / "analyzer.py",
        root / "src" / "renderer.py",
        root / "src" / "cli.py",
    ]

    for path in expected:
        assert path.exists(), f"missing expected module: {path}"


def test_cli_can_be_imported() -> None:
    module = import_module("src.cli")
    assert hasattr(module, "main")


def test_project_docs_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "requirements.txt").exists()
    assert (root / "README.md").exists()
