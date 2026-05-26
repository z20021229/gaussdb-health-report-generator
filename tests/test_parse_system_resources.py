from pathlib import Path

import pytest
import yaml

from src.archive_extractor import ArchiveExtractionError, extract_package
from src.inspection_parser import parse_inspection_files


def test_parse_system_resource_nodes_from_sample_package() -> None:
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

    nodes = data["nodes"]
    assert isinstance(nodes, list)
    assert "resource_summary" in data["cluster"]

    for node in nodes:
        assert node.get("ip") or node.get("hostname")

        memory = node.get("memory", {})
        assert "total_mb" in memory
        assert "used_mb" in memory
        assert "usage_percent" in memory

        assert isinstance(node.get("disks", []), list)
        assert isinstance(node.get("cpu_cores"), int) or node.get("cpu_cores") == "未采集"

    if nodes:
        assert data["cluster"]["resource_summary"]["node_count"] == len(nodes)
