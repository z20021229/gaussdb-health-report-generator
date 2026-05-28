from pathlib import Path

from docx import Document
from PIL import Image

from src.analyzer import analyze_inspection_data
from src.archive_extractor import extract_package
from src.evidence_image_builder import build_evidence_images
from src.inspection_parser import parse_inspection_files
from src.renderer import render_docx


def test_render_docx_with_minimal_data(tmp_path: Path) -> None:
    image_path = _create_image(tmp_path / "evidence" / "os_01.png")
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

    assert output_path.exists()
    assert output_path.stat().st_size > 0

    document = Document(output_path)
    text = _document_text(document)
    for required_text in [
        "第一章 总结",
        "第二章 系统概况",
        "第三章 总体情况",
        "第四章 高可用检查",
        "第五章 参数检查",
        "第六章 系统管理维护",
        "附录 原始依据与截图",
        "风险级问题明细",
        "关注级问题明细",
        "整改建议汇总",
        "检查结果：",
    ]:
        assert required_text in text


def test_render_docx_keeps_all_risk_and_warning_details(tmp_path: Path) -> None:
    image_paths = [
        _create_image(tmp_path / "evidence" / f"os_{index}.png")
        for index in range(1, 4)
    ]
    risks = [
        {
            "level": "风险",
            "item": "磁盘空间",
            "detail": f"风险问题{index:02d}",
            "suggestion": "建议处理风险问题",
            "source": f"来源{index:02d}",
        }
        for index in range(1, 16)
    ]
    warnings = [
        {
            "level": "关注",
            "item": "CPU 使用率",
            "detail": f"关注问题{index:02d}",
            "suggestion": "建议持续观察",
            "source": f"关注来源{index:02d}",
        }
        for index in range(1, 13)
    ]
    data = _base_report_data(
        risks=risks,
        warnings=warnings,
        evidence_items=[
            {
                "type": "section_text",
                "title": f"操作系统信息 - 第{index}页",
                "section_name": "操作系统信息",
                "source_file": "sample/inspection_rec.txt",
                "image_path": str(path),
                "status": "success",
                "error": "",
            }
            for index, path in enumerate(image_paths, start=1)
        ],
    )
    output_path = tmp_path / "full-risk-report.docx"

    render_docx(data, output_path)

    document = Document(output_path)
    text = _document_text(document)
    for risk in risks:
        assert risk["detail"] in text
    for warning in warnings:
        assert warning["detail"] in text
    assert len(document.inline_shapes) >= 3


def test_render_docx_with_real_sample_data(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    sample_input = root / "samples" / "收益所有人.rar"
    template_path = root / "templates" / "GaussDB数据库健康诊断报告.docx"
    assert sample_input.exists()
    assert template_path.exists()

    workdir = tmp_path / "workdir"
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = extract_package(str(sample_input), str(workdir))
    inspection_files = manifest.get("files", {}).get("inspection_rec", [])
    data = parse_inspection_files(inspection_files, manifest=manifest, output_dir=output_dir)
    data["report"]["source_package"] = str(sample_input)
    data["report"]["template_file"] = str(template_path)
    data["report"]["extracted_manifest_path"] = str(output_dir / "extracted_manifest.yaml")
    data = analyze_inspection_data(data)
    evidence = build_evidence_images(data, manifest, str(output_dir))
    data["evidence_images"] = {
        "manifest_path": evidence["manifest_path"],
        "evidence_images_dir": evidence["evidence_images_dir"],
        "items": evidence["items"],
    }

    output_path = tmp_path / "real-sample-report.docx"
    render_docx(data, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0

    document = Document(output_path)
    text = _document_text(document)
    for required_text in [
        "第一章 总结",
        "第二章 系统概况",
        "第三章 总体情况",
        "第四章 高可用检查",
        "第五章 参数检查",
        "第六章 系统管理维护",
        "附录 原始依据与截图",
        "风险级问题明细",
        "关注级问题明细",
        "整改建议汇总",
    ]:
        assert required_text in text

    section_text_items = [
        item
        for item in data["evidence_images"]["items"]
        if item.get("type") == "section_text" and item.get("status") == "success"
    ]
    assert section_text_items
    assert len(document.inline_shapes) > 0
    assert "检查结果：" in text

    html_failed_items = [
        item
        for item in data["evidence_images"]["items"]
        if item.get("type") == "html_screenshot" and item.get("status") != "success"
    ]
    if html_failed_items:
        for item in html_failed_items:
            assert item["source_file"] in text
            if item.get("error"):
                assert item["error"] in text


def _base_report_data(
    *,
    risks: list[dict] | None = None,
    warnings: list[dict] | None = None,
    evidence_items: list[dict] | None = None,
) -> dict:
    risks = risks or [
        {
            "level": "风险",
            "item": "高可用同步",
            "detail": "同步位点存在差异",
            "suggestion": "建议核查复制链路状态",
            "source": "高可用状态检查",
        }
    ]
    warnings = warnings or [
        {
            "level": "关注",
            "item": "大表容量",
            "detail": "存在大表，建议持续关注容量增长趋势",
            "suggestion": "建议结合业务增长趋势评估归档或分区策略",
            "source": "大表检查",
        }
    ]
    all_risks = [*risks, *warnings]
    suggestion_rows = {}
    for item in all_risks:
        key = (item["level"], item["item"], item["suggestion"])
        suggestion_rows[key] = suggestion_rows.get(key, 0) + 1

    suggestions = [
        {
            "level": level,
            "item": item_name,
            "suggestion": suggestion,
            "related_count": count,
        }
        for (level, item_name, suggestion), count in suggestion_rows.items()
    ]

    return {
        "report": {
            "title": "GaussDB 数据库健康诊断报告",
            "customer_name": "未提供",
            "inspector": "未提供",
            "inspection_date": "未采集",
            "generated_at": "2026-05-28T10:00:00+08:00",
            "source_package": "samples/demo.rar",
            "source_files": ["sample/inspection_rec.txt"],
            "extracted_manifest_path": "output/extracted_manifest.yaml",
        },
        "sections": {"parsed_sections": []},
        "nodes": [
            {
                "ip": "10.0.0.1",
                "hostname": "node-a",
                "role": "未采集",
                "os_version": "openEuler 22.03",
                "architecture": "x86_64",
                "os_summary": "Linux node-a 5.10 x86_64 GNU/Linux",
                "cpu_model": "CPU Demo",
                "cpu_cores": 16,
                "threads_per_core": "2",
                "cores_per_socket": "8",
                "sockets": "1",
                "numa_nodes": "1",
                "memory": {
                    "total_mb": 32768,
                    "used_mb": 16384,
                    "free_mb": 4096,
                    "available_mb": 12288,
                    "usage_percent": 50.0,
                },
                "disks": [
                    {
                        "filesystem": "/dev/vda1",
                        "size": "500G",
                        "used": "300G",
                        "avail": "200G",
                        "use_percent": 60,
                        "mounted_on": "/data",
                    }
                ],
                "disk_summary": {
                    "max_disk_use_percent": 60,
                    "data_disk_use_percent": 60,
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
            "overall_status": "风险" if risks else "关注",
            "ha_status": [
                {
                    "client_addr": "10.0.0.2",
                    "sync_state": "Sync",
                    "pg_xlog_location_diff": "0",
                }
            ],
            "ha_summary": "已解析 1 条高可用状态记录",
            "replication_slots": [
                {
                    "slot_name": "slot_demo",
                    "slot_type": "physical",
                    "active": "true",
                    "delay_lsn": "0",
                }
            ],
            "replication_slot_summary": "已解析 1 条复制槽记录",
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
                        "raw_detail_path": "output/raw_sections/check_dir.txt",
                    }
                ],
            },
            "resource_summary": {
                "node_count": 1,
                "cluster_max_disk_use_percent": 60,
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
                        "conf_reload_time": "2026-05-27 10:00:00",
                        "is_in_recovery": "false",
                        "role_hint": "主库",
                    }
                ],
                "summary": "已解析 1 条数据库运行状态记录",
            },
            "databases": [
                {
                    "datname": "postgres",
                    "size_bytes": 1024 * 1024 * 512,
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
                    "bytes": 1024,
                    "relsize": "1 GB",
                    "indexsize": "256 MB",
                }
            ],
            "large_tables_summary": "已解析 1 条大表记录",
            "index_suggestions": [
                {
                    "tablename": "public.demo",
                    "table_size": "512 MB",
                    "seq_scan": 100,
                    "idx_scan": 2,
                    "rate": "50:1",
                }
            ],
            "index_suggestions_summary": "已解析 1 条索引建议记录",
            "unused_indexes": [],
            "unused_indexes_summary": "未发现未使用索引",
            "table_bloat": [
                {
                    "schemaname": "public",
                    "relname": "demo",
                    "n_live_tup": 1000,
                    "n_dead_tup": 200,
                    "dead_rate": "20%",
                }
            ],
            "table_bloat_summary": "已解析 1 条表膨胀记录",
        },
        "logs": {
            "fatal_log_summary": "未发现 fatal 异常日志",
            "panic_log_summary": "未发现 panic 异常日志",
            "fatal_log_files": [],
            "panic_log_files": [],
        },
        "risks": all_risks,
        "risk_summary": {
            "total_count": len(all_risks),
            "risk_count": len(risks),
            "warning_count": len(warnings),
            "by_item": _build_summary_by_item(risks, warnings),
            "by_source": [],
        },
        "risk_details": {
            "risks": risks,
            "warnings": warnings,
        },
        "conclusion": {
            "summary": [
                "本次巡检已完成系统资源、数据库运行状态、高可用状态及系统管理维护类项目检查。",
                "建议结合风险项与关注项逐项制定整改计划并持续跟踪。",
            ],
            "suggestions": suggestions,
        },
        "evidence_images": {
            "manifest_path": "output/evidence_images_manifest.yaml",
            "evidence_images_dir": "output/evidence_images",
            "items": evidence_items or [],
        },
    }


def _build_summary_by_item(risks: list[dict], warnings: list[dict]) -> list[dict]:
    items: dict[str, dict[str, int | str]] = {}
    for risk in risks:
        row = items.setdefault(
            risk["item"],
            {"item": risk["item"], "risk_count": 0, "warning_count": 0, "total_count": 0},
        )
        row["risk_count"] += 1
        row["total_count"] += 1
    for warning in warnings:
        row = items.setdefault(
            warning["item"],
            {"item": warning["item"], "risk_count": 0, "warning_count": 0, "total_count": 0},
        )
        row["warning_count"] += 1
        row["total_count"] += 1
    return list(items.values())


def _create_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 80), "white").save(path)
    return path


def _document_text(document: Document) -> str:
    parts: list[str] = []
    parts.extend(paragraph.text for paragraph in document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)
