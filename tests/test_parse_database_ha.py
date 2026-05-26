from pathlib import Path

import pytest
import yaml

from src.archive_extractor import ArchiveExtractionError, extract_package
from src.inspection_parser import parse_inspection_files


def test_parse_database_and_ha_sections_from_sample_package() -> None:
    root = Path(__file__).resolve().parents[1]
    sample = root / "samples" / "收益所有人.rar"
    output_yaml = root / "output" / "inspection_data.generated.yaml"

    try:
        manifest = extract_package(str(sample), str(root / "workdir"))
    except ArchiveExtractionError as exc:
        pytest.skip(f"RAR extraction dependency is unavailable or failed: {exc}")

    data = parse_inspection_files(manifest["files"]["inspection_rec"])
    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    output_yaml.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    assert isinstance(data["cluster"]["ha_status"], list)
    assert isinstance(data["cluster"]["replication_slots"], list)
    assert isinstance(data["database"]["running_status"], dict)
    assert isinstance(data["database"]["databases"], list)
    assert "version" in data["database"]

    for record in data["cluster"]["ha_status"]:
        assert "client_addr" in record
        assert "sync_state" in record
        assert "pg_xlog_location_diff" in record

    for record in data["cluster"]["replication_slots"]:
        assert "slot_name" in record
        assert "slot_type" in record
        assert "active" in record
        assert "delay_lsn" in record

    for record in data["database"]["databases"]:
        assert "datname" in record
        assert "size_bytes" in record
        assert "readable_size" in record
