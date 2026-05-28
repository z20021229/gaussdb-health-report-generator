"""Build evidence images from parsed inspection sections and extracted files."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - environment-dependent
    sync_playwright = None


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600
MARGIN_X = 40
MARGIN_Y = 40
LINE_SPACING = 10
TEXT_FILL = "#111111"
BG_FILL = "#f7f7f7"


def build_evidence_images(data: dict, extracted_manifest: dict, output_dir: str) -> dict:
    """Create evidence images and a manifest without failing the main pipeline."""
    output_root = Path(output_dir)
    evidence_dir = output_root / "evidence_images"
    manifest_path = output_root / "evidence_images_manifest.yaml"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    items.extend(_build_section_text_images(data, evidence_dir))
    items.extend(_build_html_screenshots(extracted_manifest, evidence_dir))
    items.extend(_collect_existing_images(extracted_manifest, evidence_dir))

    result = {
        "manifest_path": str(manifest_path),
        "evidence_images_dir": str(evidence_dir),
        "items": items,
    }
    manifest_path.write_text(
        yaml.safe_dump(result, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return result


def _build_section_text_images(data: dict, evidence_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    sections = (data.get("sections") or {}).get("parsed_sections") or []
    font = _load_font()
    header_font = _load_font(size=30)

    for section_index, section in enumerate(sections, start=1):
        section_name = str(section.get("section_name", "未识别章节"))
        source_file = str(section.get("source_file", "未采集"))
        content = str(section.get("content", "")).strip() or "该章节未采集到原始输出"
        pages = _paginate_section_text(section_name, source_file, content, font, header_font)
        safe_base = _safe_name(f"{section_index:03d}_{section_name}")
        for page_index, page_lines in enumerate(pages, start=1):
            image_path = evidence_dir / f"{safe_base}_p{page_index:02d}.png"
            _render_text_page(image_path, page_lines, font, header_font)
            items.append(
                {
                    "type": "section_text",
                    "title": f"{section_name} - 第{page_index}页",
                    "section_name": section_name,
                    "source_file": source_file,
                    "image_path": str(image_path),
                    "status": "success",
                    "error": "",
                }
            )
    return items


def _build_html_screenshots(extracted_manifest: dict, evidence_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    files = extracted_manifest.get("files", {}) if isinstance(extracted_manifest, dict) else {}
    html_paths: list[str] = []
    for key in ["wdr_node", "wdr_cluster", "html"]:
        html_paths.extend(files.get(key) or [])

    seen: set[str] = set()
    unique_paths = [path for path in html_paths if not (path in seen or seen.add(path))]

    if not unique_paths:
        return items

    if sync_playwright is None:
        for html_path in unique_paths:
            items.append(
                {
                    "type": "html_screenshot",
                    "title": Path(html_path).name,
                    "section_name": "",
                    "source_file": html_path,
                    "image_path": "",
                    "status": "failed",
                    "error": "Playwright Python package is not installed.",
                }
            )
        return items

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            for html_path in unique_paths:
                target = Path(html_path)
                image_path = evidence_dir / f"{_safe_name(target.stem)}_html.png"
                try:
                    page.goto(target.resolve().as_uri(), wait_until="load")
                    page.screenshot(path=str(image_path), full_page=True)
                    items.append(
                        {
                            "type": "html_screenshot",
                            "title": target.name,
                            "section_name": "",
                            "source_file": str(target),
                            "image_path": str(image_path),
                            "status": "success",
                            "error": "",
                        }
                    )
                except Exception as exc:  # pragma: no cover - browser dependent
                    items.append(
                        {
                            "type": "html_screenshot",
                            "title": target.name,
                            "section_name": "",
                            "source_file": str(target),
                            "image_path": "",
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
            browser.close()
    except Exception as exc:  # pragma: no cover - browser dependent
        for html_path in unique_paths:
            items.append(
                {
                    "type": "html_screenshot",
                    "title": Path(html_path).name,
                    "section_name": "",
                    "source_file": html_path,
                    "image_path": "",
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return items


def _collect_existing_images(extracted_manifest: dict, evidence_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    extract_root = Path(str(extracted_manifest.get("extract_root", ""))) if extracted_manifest else Path()
    if not extract_root.exists():
        return items

    for image_path in sorted(path for path in extract_root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES):
        copied_path = evidence_dir / f"{_safe_name(image_path.stem)}{image_path.suffix.lower()}"
        shutil.copy2(image_path, copied_path)
        items.append(
            {
                "type": "existing_image",
                "title": image_path.name,
                "section_name": "",
                "source_file": str(image_path),
                "image_path": str(copied_path),
                "status": "success",
                "error": "",
            }
        )
    return items


def _paginate_section_text(
    section_name: str,
    source_file: str,
    content: str,
    font: ImageFont.ImageFont,
    header_font: ImageFont.ImageFont,
) -> list[list[str]]:
    _ = source_file
    header_lines = [f"章节名称: {section_name}", "检查输出:", ""]
    wrapped_lines: list[str] = []
    for line in content.splitlines() or [""]:
        wrapped_lines.extend(_wrap_line(line, font, PAGE_WIDTH - MARGIN_X * 2))
    all_lines = header_lines + wrapped_lines

    line_height = _line_height(font)
    header_height = _line_height(header_font)
    available_height = PAGE_HEIGHT - MARGIN_Y * 2
    first_page_capacity = max(1, (available_height - header_height * 2) // (line_height + LINE_SPACING))
    page_capacity = max(1, available_height // (line_height + LINE_SPACING))

    pages: list[list[str]] = []
    cursor = 0
    first_page = True
    while cursor < len(all_lines):
        capacity = first_page_capacity if first_page else page_capacity
        pages.append(all_lines[cursor : cursor + capacity])
        cursor += capacity
        first_page = False
    return pages or [[f"章节名称: {section_name}", "检查输出:", "", "该章节未采集到原始输出"]]


def _render_text_page(
    image_path: Path,
    lines: list[str],
    font: ImageFont.ImageFont,
    header_font: ImageFont.ImageFont,
) -> None:
    image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), BG_FILL)
    draw = ImageDraw.Draw(image)
    y = MARGIN_Y
    for index, line in enumerate(lines):
        current_font = header_font if index < 2 else font
        draw.text((MARGIN_X, y), line, font=current_font, fill=TEXT_FILL)
        y += _line_height(current_font) + LINE_SPACING
    image.save(image_path)


def _wrap_line(line: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not line:
        return [""]

    chunks: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if _text_width(candidate, font) <= max_width or not current:
            current = candidate
            continue
        chunks.append(current)
        current = char
    if current:
        chunks.append(current)
    return chunks


def _text_width(text: str, font: ImageFont.ImageFont) -> int:
    bbox = font.getbbox(text or " ")
    return bbox[2] - bbox[0]


def _line_height(font: ImageFont.ImageFont) -> int:
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]


def _load_font(size: int = 24) -> ImageFont.ImageFont:
    font_candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for candidate in font_candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def _safe_name(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return safe.strip("._") or "evidence"
