from pathlib import Path

import pytest
import yaml

from src.archive_extractor import ArchiveExtractionError, extract_package
from src.inspection_parser import parse_inspection_files


def test_parse_inspection_rec_sections_from_sample_package() -> None:
    root = Path(__file__).resolve().parents[1]
    sample = root / "samples" / "收益所有人.rar"
    output_yaml = root / "output" / "inspection_data.generated.yaml"

    try:
        manifest = extract_package(str(sample), str(root / "workdir"))
    except ArchiveExtractionError as exc:
        pytest.skip(f"RAR extraction dependency is unavailable or failed: {exc}")

    inspection_files = manifest["files"]["inspection_rec"]
    data = parse_inspection_files(inspection_files)

    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    output_yaml.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    assert output_yaml.exists()
    for key in ["report", "sections", "nodes", "cluster", "database", "logs", "risks", "conclusion"]:
        assert key in data

    parsed_sections = data["sections"]["parsed_sections"]
    assert isinstance(parsed_sections, list)
    assert len(parsed_sections) > 1

    for section in parsed_sections:
        assert "source_file" in section
        assert "section_name" in section
        assert "content" in section
        assert "content_preview" in section
        assert section["content"] or section["content_preview"] or section["section_name"]
