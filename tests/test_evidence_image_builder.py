from pathlib import Path

import yaml
from PIL import Image

from src.evidence_image_builder import build_evidence_images


def test_builds_section_text_images_and_manifest(tmp_path: Path) -> None:
    data = {
        "sections": {
            "parsed_sections": [
                {
                    "section_name": "测试章节",
                    "source_file": "sample/inspection_rec.txt",
                    "content": "第一行\n第二行\n第三行",
                    "content_preview": "第一行 第二行 第三行",
                }
            ]
        }
    }
    manifest = {"extract_root": str(tmp_path / "extract"), "files": {"html": []}}
    result = build_evidence_images(data, manifest, str(tmp_path / "output"))

    assert Path(result["manifest_path"]).exists()
    section_items = [item for item in result["items"] if item["type"] == "section_text"]
    assert len(section_items) >= 1
    assert Path(section_items[0]["image_path"]).exists()
    assert Path(section_items[0]["image_path"]).stat().st_size > 0


def test_long_text_is_split_into_multiple_images(tmp_path: Path) -> None:
    long_text = "\n".join(f"第{i}行 " + ("内容" * 80) for i in range(200))
    data = {
        "sections": {
            "parsed_sections": [
                {
                    "section_name": "超长章节",
                    "source_file": "sample/inspection_rec.txt",
                    "content": long_text,
                    "content_preview": "超长章节",
                }
            ]
        }
    }
    manifest = {"extract_root": str(tmp_path / "extract"), "files": {"html": []}}
    result = build_evidence_images(data, manifest, str(tmp_path / "output"))
    section_items = [item for item in result["items"] if item["type"] == "section_text"]
    assert len(section_items) > 1


def test_missing_html_files_do_not_fail(tmp_path: Path) -> None:
    data = {"sections": {"parsed_sections": []}}
    manifest = {"extract_root": str(tmp_path / "extract"), "files": {"html": []}}
    result = build_evidence_images(data, manifest, str(tmp_path / "output"))
    assert isinstance(result["items"], list)


def test_html_screenshot_failure_is_recorded_when_browser_unavailable(tmp_path: Path) -> None:
    html_root = tmp_path / "extract"
    html_root.mkdir(parents=True, exist_ok=True)
    html_file = html_root / "sample.html"
    html_file.write_text("<html><body><h1>Hello</h1></body></html>", encoding="utf-8")

    data = {"sections": {"parsed_sections": []}}
    manifest = {"extract_root": str(html_root), "files": {"html": [str(html_file)]}}
    result = build_evidence_images(data, manifest, str(tmp_path / "output"))
    html_items = [item for item in result["items"] if item["type"] == "html_screenshot"]
    assert len(html_items) == 1
    assert html_items[0]["status"] in {"success", "failed", "skipped"}
    if html_items[0]["status"] != "success":
        assert html_items[0]["error"]


def test_existing_images_are_copied(tmp_path: Path) -> None:
    extract_root = tmp_path / "extract"
    extract_root.mkdir(parents=True, exist_ok=True)
    source_image = extract_root / "source.png"
    Image.new("RGB", (20, 20), "white").save(source_image)

    data = {"sections": {"parsed_sections": []}}
    manifest = {"extract_root": str(extract_root), "files": {"html": []}}
    result = build_evidence_images(data, manifest, str(tmp_path / "output"))
    existing_items = [item for item in result["items"] if item["type"] == "existing_image"]
    assert len(existing_items) == 1
    assert Path(existing_items[0]["image_path"]).exists()


def test_manifest_yaml_is_written(tmp_path: Path) -> None:
    data = {"sections": {"parsed_sections": []}}
    manifest = {"extract_root": str(tmp_path / "extract"), "files": {"html": []}}
    result = build_evidence_images(data, manifest, str(tmp_path / "output"))
    manifest_path = Path(result["manifest_path"])
    loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert "items" in loaded
