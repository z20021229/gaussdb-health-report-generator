from pathlib import Path

from docx import Document
from PIL import Image

from src.analyzer import analyze_inspection_data
from src.archive_extractor import extract_package
from src.evidence_image_builder import build_evidence_images
from src.inspection_parser import parse_inspection_files
from src.renderer import render_docx


def test_render_docx_uses_template_chapters_without_appendix(tmp_path: Path) -> None:
    image_path = _create_image(tmp_path / "evidence" / "os.png")
    data = _base_report_data(
        evidence_items=[
            {
                "type": "section_text",
                "title": "操作系统信息 - 第1页",
                "section_name": "操作系统信息",
                "source_file": "sample/inspection_rec.txt",
                "image_path": str(image_path),
                "status": "success",
                "error": "",
            }
        ]
    )
    output_path = tmp_path / "report.docx"

    render_docx(data, output_path)

    document = Document(output_path)
    text = _document_text(document)

    for chapter in [
        "第一章 总结",
        "第二章 系统概况",
        "第三章 总体情况",
        "第四章 高可用检查",
        "第五章 参数检查",
        "第六章 系统管理维护",
    ]:
        assert chapter in text

    assert "附录 原始依据与截图" not in text
    for banned in [
        "workdir",
        "output",
        "raw_sections",
        "manifest",
        ".yaml",
        "parser",
        "analyzer",
        "renderer",
        "风险级问题明细",
        "关注级问题明细",
        "raw_detail_path",
    ]:
        assert banned not in text


def test_render_docx_marks_disk_25_percent_as_good(tmp_path: Path) -> None:
    data = _base_report_data()
    data["nodes"][0]["disks"][0]["use_percent"] = 25
    data["nodes"][0]["disk_summary"]["max_disk_use_percent"] = 25
    data["cluster"]["resource_summary"]["cluster_max_disk_use_percent"] = 25
    output_path = tmp_path / "disk.docx"

    render_docx(data, output_path)

    text = _document_text(Document(output_path))
    assert "磁盘空间整体状态为良好" in text
    assert "风险" not in text.split("3.2 磁盘空间概况", 1)[1][:120]


def test_database_version_without_screenshot_does_not_borrow_database_info_image(tmp_path: Path) -> None:
    db_info_image = _create_image(tmp_path / "evidence" / "database_info.png")
    data = _base_report_data(
        evidence_items=[
            {
                "type": "section_text",
                "title": "数据库信息检查 - 第1页",
                "section_name": "数据库信息检查",
                "source_file": "sample/inspection_rec.txt",
                "image_path": str(db_info_image),
                "status": "success",
                "error": "",
            }
        ]
    )
    output_path = tmp_path / "database-version.docx"

    render_docx(data, output_path)

    document = Document(output_path)
    text = _document_text(document)
    assert "2.2 数据库版本检查" in text
    assert "检查结果未采集。" in text
    assert len(document.inline_shapes) == 1


def test_gs_check_and_table_bloat_stay_in_their_own_chapters(tmp_path: Path) -> None:
    data = _base_report_data()
    output_path = tmp_path / "sections.docx"

    render_docx(data, output_path)

    text = _document_text(Document(output_path))
    assert "第五章 参数检查" in text
    assert "CheckDirPermissions" in text
    assert "第六章 系统管理维护" in text
    assert "public" in text
    assert "6.4 表膨胀检查" in text


def test_empty_fatal_and_panic_logs_do_not_render_as_exceptions(tmp_path: Path) -> None:
    data = _base_report_data()
    output_path = tmp_path / "logs.docx"

    render_docx(data, output_path)

    text = _document_text(Document(output_path))
    assert "未发现 fatal 异常日志" in text
    assert "未发现 panic 异常日志" in text
    assert "日志文件缺失" not in text


def test_render_real_sample_docx_without_engineering_terms(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    sample_input = root / "samples" / "收益所有人.rar"
    template_path = root / "templates" / "GaussDB数据库健康诊断报告.docx"
    workdir = tmp_path / "workdir"
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = extract_package(str(sample_input), str(workdir))
    inspection_files = manifest.get("files", {}).get("inspection_rec", [])
    data = parse_inspection_files(inspection_files, manifest=manifest, output_dir=output_dir)
    data["report"]["source_package"] = str(sample_input)
    data["report"]["template_file"] = str(template_path)
    data = analyze_inspection_data(data)
    evidence = build_evidence_images(data, manifest, str(output_dir))
    data["evidence_images"] = {
        "manifest_path": evidence["manifest_path"],
        "evidence_images_dir": evidence["evidence_images_dir"],
        "items": evidence["items"],
    }

    output_path = tmp_path / "real.docx"
    render_docx(data, output_path)

    document = Document(output_path)
    text = _document_text(document)
    assert "附录 原始依据与截图" not in text
    for banned in [
        "workdir",
        "output",
        "raw_sections",
        "evidence_images_manifest",
        "inspection_data.generated.yaml",
        "raw_detail_path",
        "source_file：",
        "来源文件：",
    ]:
        assert banned not in text


def _base_report_data(
    *,
    evidence_items: list[dict] | None = None,
) -> dict:
    data = {
        "report": {
            "title": "GaussDB 数据库健康诊断报告",
            "inspector": "未提供",
            "inspection_date": "未采集",
            "source_package": "samples/demo.rar",
            "source_files": ["samples/demo_20260521.txt"],
        },
        "nodes": [
            {
                "ip": "10.0.0.1",
                "hostname": "node-a",
                "role": "未采集",
                "os_version": "openEuler 22.03",
                "architecture": "x86_64",
                "cpu_model": "CPU Demo",
                "cpu_cores": 16,
                "threads_per_core": "2",
                "sockets": "1",
                "numa_nodes": "1",
                "memory": {"usage_percent": 50.0},
                "disks": [
                    {
                        "filesystem": "/dev/vda1",
                        "size": "500G",
                        "used": "125G",
                        "avail": "375G",
                        "use_percent": 25,
                        "mounted_on": "/data",
                    }
                ],
                "disk_summary": {
                    "max_disk_use_percent": 25,
                    "data_disk_use_percent": 25,
                    "max_disk_mount": "/data",
                },
                "cpu_daily": {
                    "avg_user": 8.2,
                    "avg_system": 2.3,
                    "avg_iowait": 0.4,
                    "avg_idle": 89.1,
                    "min_idle": 80.0,
                    "max_iowait": 1.2,
                },
            }
        ],
        "cluster": {
            "cluster_status": "未采集",
            "overall_status": "关注",
            "ha_status": [
                {"client_addr": "10.0.0.2", "sync_state": "Sync", "pg_xlog_location_diff": "0"}
            ],
            "ha_summary": "已完成高可用状态检查。",
            "replication_slots": [
                {"slot_name": "slot_demo", "slot_type": "physical", "active": "true", "delay_lsn": "0"}
            ],
            "replication_slot_summary": "复制槽状态正常。",
            "gs_check_summary": {
                "ok_count": 3,
                "ng_count": 1,
                "na_count": 0,
                "unknown_count": 0,
                "ng_items": [
                    {
                        "check_name": "CheckDirPermissions",
                        "status": "NG",
                        "detail_summary": "目录权限需要进一步核查",
                        "raw_detail_path": "ignored",
                    }
                ],
                "ng_display_items": [
                    {
                        "check_name": "CheckDirPermissions",
                        "status": "NG",
                        "detail_summary": "目录权限需要进一步核查",
                        "suggestion": "建议根据安全规范核查目录权限，避免权限过宽。",
                    }
                ],
            },
            "resource_summary": {
                "node_count": 1,
                "cluster_max_disk_use_percent": 25,
                "cluster_min_cpu_idle": 80.0,
                "cluster_max_iowait": 1.2,
            },
        },
        "database": {
            "version": "GaussDB 5.x",
            "running_status": {
                "records": [
                    {
                        "checktime": "2026-05-28 10:00:00",
                        "uptime": "10 days",
                        "lsn": "0/16B6C50",
                        "insert_lsn": "0/16B6C50",
                        "write_lsn": "0/16B6C50",
                        "is_in_recovery": "false",
                    }
                ],
                "summary": "数据库运行状态检查正常。",
            },
            "databases": [
                {
                    "datname": "postgres",
                    "readable_size": "512.00 MB",
                    "age": "12345",
                    "is_template": "f",
                    "allow_conn": "t",
                    "conn_limit": "-1",
                }
            ],
            "large_tables": [
                {
                    "datname": "postgres",
                    "nspname": "public",
                    "relname": "big_table",
                    "relsize": "1 GB",
                    "indexsize": "256 MB",
                }
            ],
            "large_tables_summary": "已识别 1 条大表记录",
            "unused_indexes": [],
            "unused_indexes_summary": "未发现未使用索引",
            "index_suggestions": [
                {
                    "tablename": "public.demo",
                    "table_size": "512 MB",
                    "seq_scan": 100,
                    "idx_scan": 2,
                    "rate": "50:1",
                }
            ],
            "index_suggestions_summary": "已识别 1 条索引建议记录",
            "table_bloat": [
                {
                    "schemaname": "public",
                    "relname": "demo",
                    "n_live_tup": 1000,
                    "n_dead_tup": 200,
                    "dead_rate": "20%",
                }
            ],
            "table_bloat_summary": "已识别 1 条表膨胀记录",
        },
        "logs": {
            "fatal_log_summary": "未发现 fatal 异常日志",
            "panic_log_summary": "未发现 panic 异常日志",
        },
        "risks": [
            {
                "level": "关注",
                "item": "表膨胀",
                "detail": "对象 public.demo 死元组占比为 20%",
                "suggestion": "建议结合维护窗口执行 VACUUM / ANALYZE 或表维护操作。",
                "source": {"schemaname": "public", "relname": "demo"},
            }
        ],
        "evidence_images": {
            "items": evidence_items or [],
        },
    }
    return data


def _create_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 80), "white").save(path)
    return path


def _document_text(document: Document) -> str:
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)
