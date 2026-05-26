from pathlib import Path

import yaml

from src.analyzer import analyze_inspection_data


def test_risks_and_risk_details_keep_all_entries() -> None:
    data = _base_data()
    data["cluster"]["gs_check_summary"]["ng_items"] = [
        {"check_name": f"CheckDemo{i}", "status": "NG", "detail_summary": f"问题{i}", "raw_detail_path": ""}
        for i in range(15)
    ]
    analyzed = analyze_inspection_data(data)
    detail_count = len(analyzed["risk_details"]["risks"]) + len(analyzed["risk_details"]["warnings"])
    assert len(analyzed["risks"]) == 15
    assert detail_count == 15


def test_risk_summary_counts_levels_correctly() -> None:
    data = _base_data()
    data["nodes"][0]["disks"] = [{"mounted_on": "/data", "use_percent": 85}]
    data["nodes"].append(
        {"ip": "10.0.0.2", "hostname": "n2", "memory": {"usage_percent": 0}, "disks": [{"mounted_on": "/data", "use_percent": 75}], "cpu_daily": {"avg_idle": 80, "max_iowait": 1}}
    )
    analyzed = analyze_inspection_data(data)
    assert analyzed["risk_summary"]["total_count"] == len(analyzed["risks"])
    assert analyzed["risk_summary"]["risk_count"] >= 1
    assert analyzed["risk_summary"]["warning_count"] >= 1


def test_conclusion_suggestions_merge_same_actions() -> None:
    data = _base_data()
    data["nodes"] = [
        {"ip": "10.0.0.1", "hostname": "n1", "memory": {"usage_percent": 0}, "disks": [{"mounted_on": "/data1", "use_percent": 85}], "cpu_daily": {"avg_idle": 80, "max_iowait": 1}},
        {"ip": "10.0.0.2", "hostname": "n2", "memory": {"usage_percent": 0}, "disks": [{"mounted_on": "/data2", "use_percent": 82}], "cpu_daily": {"avg_idle": 80, "max_iowait": 1}},
    ]
    analyzed = analyze_inspection_data(data)
    disk_suggestion = next(item for item in analyzed["conclusion"]["suggestions"] if item["item"] == "磁盘空间")
    assert disk_suggestion["related_count"] == 2


def test_real_sample_contains_risk_summary_and_details() -> None:
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "output" / "inspection_data.generated.yaml").read_text(encoding="utf-8"))
    analyzed = analyze_inspection_data(data)
    assert "risks" in analyzed
    assert "risk_summary" in analyzed
    assert "risk_details" in analyzed
    assert "summary" in analyzed["conclusion"]
    assert "suggestions" in analyzed["conclusion"]
    detail_count = len(analyzed["risk_details"]["risks"]) + len(analyzed["risk_details"]["warnings"])
    assert detail_count == len(analyzed["risks"])


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
