from pathlib import Path

import pytest
import yaml

from src.archive_extractor import ArchiveExtractionError, extract_package
from src.inspection_parser import parse_inspection_files


def test_parse_maintenance_checks_from_sample_package() -> None:
    root = Path(__file__).resolve().parents[1]
    sample = root / "samples" / "收益所有人.rar"
    output_yaml = root / "output" / "inspection_data.generated.yaml"

    try:
        manifest = extract_package(str(sample), str(root / "workdir"))
    except ArchiveExtractionError as exc:
        pytest.skip(f"RAR extraction dependency is unavailable or failed: {exc}")

    data = parse_inspection_files(
        manifest["files"]["inspection_rec"],
        manifest=manifest,
        output_dir=root / "output",
    )
    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    output_yaml.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    assert isinstance(data["database"]["large_tables"], list)
    assert isinstance(data["database"]["index_suggestions"], list)
    assert isinstance(data["database"]["unused_indexes"], list)
    assert isinstance(data["database"]["table_bloat"], list)

    gs_check_summary = data["cluster"]["gs_check_summary"]
    for key in ["ok_count", "ng_count", "na_count", "unknown_count", "ng_items"]:
        assert key in gs_check_summary

    assert "fatal_log_summary" in data["logs"]
    assert "panic_log_summary" in data["logs"]

    for item in gs_check_summary["ng_items"]:
        assert "check_name" in item
        assert item["status"] == "NG"
        assert "detail_summary" in item
