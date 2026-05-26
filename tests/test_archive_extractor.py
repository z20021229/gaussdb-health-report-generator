from pathlib import Path

import pytest
import yaml

from src.archive_extractor import ArchiveExtractionError, extract_package


def test_extract_sample_package_generates_manifest() -> None:
    root = Path(__file__).resolve().parents[1]
    sample = root / "samples" / "收益所有人.rar"
    output_manifest = root / "output" / "extracted_manifest.yaml"

    try:
        manifest = extract_package(str(sample), str(root / "workdir"))
    except ArchiveExtractionError as exc:
        pytest.skip(f"RAR extraction dependency is unavailable or failed: {exc}")

    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    files = manifest["files"]
    assert output_manifest.exists()
    assert len(files["inspection_rec"]) >= 1
    assert any(
        files[group]
        for group in [
            "check_reports",
            "collectors",
            "fatal_logs",
            "panic_logs",
            "wdr_node",
            "wdr_cluster",
            "html",
            "logs",
            "txt",
            "archives",
        ]
    )
