"""Command line interface for the GaussDB report generator."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from .analyzer import analyze_minimal
from .archive_extractor import ArchiveExtractionError, extract_package, prepare_workdir
from .inspection_parser import build_minimal_inspection_data
from .renderer import render_docx


DEFAULT_WORKDIR = Path("workdir")
DEFAULT_YAML_OUTPUT = Path("output") / "inspection_data.generated.yaml"
DEFAULT_MANIFEST_OUTPUT = Path("output") / "extracted_manifest.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gaussdb-report",
        description="Generate a GaussDB database health diagnosis report.",
    )
    parser.add_argument("--input", required=True, help="Path to the GaussDB inspection package.")
    parser.add_argument("--template", required=True, help="Path to the Word report template.")
    parser.add_argument("--output", required=True, help="Path to the generated Word report.")
    parser.add_argument(
        "--workdir",
        default=str(DEFAULT_WORKDIR),
        help="Working directory for intermediate files. Defaults to workdir.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    template_path = Path(args.template)
    output_path = Path(args.output)
    workdir = Path(args.workdir)

    print("[GaussDB Report] Pipeline started.")
    print(f"[GaussDB Report] Input: {input_path}")
    print(f"[GaussDB Report] Template: {template_path}")
    print(f"[GaussDB Report] Output: {output_path}")
    print(f"[GaussDB Report] Workdir: {workdir}")

    if not input_path.exists():
        parser.error(f"input file does not exist: {input_path}")
    if not template_path.exists():
        parser.error(f"template file does not exist: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prepare_workdir(workdir)

    try:
        manifest = extract_package(input_path=str(input_path), workdir=str(workdir))
    except ArchiveExtractionError as exc:
        parser.error(str(exc))

    manifest_path = DEFAULT_MANIFEST_OUTPUT
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[GaussDB Report] Generated extraction manifest: {manifest_path}")

    data = build_minimal_inspection_data(input_path=input_path, template_path=template_path)
    data = analyze_minimal(data)

    yaml_path = DEFAULT_YAML_OUTPUT
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[GaussDB Report] Generated YAML: {yaml_path}")

    render_docx(data=data, output_path=output_path)
    print(f"[GaussDB Report] Generated DOCX: {output_path}")
    print("[GaussDB Report] Pipeline completed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
