from pathlib import Path

import yaml

from src.analyzer import analyze_inspection_data


def test_risk_summary_groups_same_disk_risks() -> None:
    data = _base_data()
    data["risks"] = []
    data["nodes"] = [
        {"ip": "10.0.0.1", "hostname": "n1", "memory": {"usage_percent": 0}, "disks": [{"mounted_on": "/data", "use_percent": 85}], "cpu_daily": {"avg_idle": 80, "max_iowait": 1}},
        {"ip": "10.0.0.2", "hostname": "n2", "memory": {"usage_percent": 0}, "disks": [{"mounted_on": "/data", "use_percent": 82}], "cpu_daily": {"avg_idle": 80, "max_iowait": 1}},
    ]
    analyzed = analyze_inspection_data(data)
    grouped = [item for item in analyzed["risk_summary"]["grouped"] if item["item"] == "磁盘空间"]
    assert len(grouped) == 1
    assert grouped[0]["count"] == 2
    assert len([risk for risk in analyzed["risks"] if risk["item"] == "磁盘空间"]) == 2


def test_report_risks_is_capped_at_ten() -> None:
    data = _base_data()
    data["cluster"]["gs_check_summary"]["ng_items"] = [
        {"check_name": f"CheckDemo{i}", "status": "NG", "detail_summary": f"问题{i}", "raw_detail_path": ""}
        for i in range(12)
    ]
    analyzed = analyze_inspection_data(data)
    assert len(analyzed["report_risks"]) <= 10


def test_report_risks_includes_gs_check_items() -> None:
    data = _base_data()
    data["cluster"]["gs_check_summary"]["ng_items"] = [
        {"check_name": "CheckDirPermissions", "status": "NG", "detail_summary": "目录权限异常", "raw_detail_path": ""}
    ]
    analyzed = analyze_inspection_data(data)
    assert any("gs_check -" in item["item"] for item in analyzed["report_risks"])


def test_real_sample_contains_risk_summary_and_report_risks() -> None:
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "output" / "inspection_data.generated.yaml").read_text(encoding="utf-8"))
    analyzed = analyze_inspection_data(data)
    assert "risks" in analyzed
    assert "risk_summary" in analyzed
    assert "report_risks" in analyzed
    assert "summary" in analyzed["conclusion"]
    assert "suggestions" in analyzed["conclusion"]
    assert len(analyzed["report_risks"]) <= 10


def _base_data() -> dict:
    return {
        "nodes": [
            {
                "ip": "10.0.0.1",
                "hostname": "node1",
                "memory": {"usage_percent": 0},
                "disks": [{"mounted_on": "/data", "use_percent": 20}],
                "cpu_daily": {"avg_idle": 80, "max_iowait": 1},
            }
        ],
        "cluster": {
            "cluster_status": "normal",
            "ha_status": [],
            "replication_slots": [],
            "gs_check_summary": {
                "ok_count": 0,
                "ng_count": 0,
                "na_count": 0,
                "unknown_count": 0,
                "ng_items": [],
            },
            "resource_summary": {"node_count": 1, "cluster_max_disk_use_percent": 0, "cluster_min_cpu_idle": 80, "cluster_max_iowait": 1},
        },
        "database": {
            "running_status": {"records": []},
            "large_tables": [],
            "index_suggestions": [],
            "unused_indexes": [],
            "table_bloat": [],
        },
        "logs": {
            "fatal_log_summary": "未发现 fatal 异常日志",
            "panic_log_summary": "未发现 panic 异常日志",
            "fatal_log_files": [],
            "panic_log_files": [],
        },
        "risks": [],
        "conclusion": {"summary": [], "suggestions": []},
    }
