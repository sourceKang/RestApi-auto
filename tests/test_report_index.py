from __future__ import annotations

import json

import yaml

from tools import build_report_index as rindex
from utils.redaction import redact_text


NODE3_IP = "192.168.169.58"
B12 = "03.00.11 (AAVV.221) b12_redhat"
B13 = "03.00.11 (AAVV.221) b13"
C0 = "03.00.11 (AAVV.221)C0_redhat"


def _write_txt(directory, name, *, generated, version, cases=(), node_ip=NODE3_IP, node_name="Taiwan_NeoX-03_169.58"):
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Report generated on: {generated}",
        f"Summary: {sum(1 for c in cases if c[2] == 'Pass')} Pass / {sum(1 for c in cases if c[2] == 'Fail')} Fail",
        f"EMS Version: {version}",
        f"Node Name: {node_name}",
        f"Node IP: {node_ip}",
        "Node Chassis: NeoX-03",
        "",
        "Test Results:",
        "-------------",
    ]
    lines += [f"[{case_id}][{case_name}] Result {result} (0.10s)" for case_id, case_name, result in cases]
    path = directory / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_allure(directory, case_id, status, steps, message=""):
    directory.mkdir(parents=True, exist_ok=True)
    result = {
        "name": f"test_{case_id}",
        "status": status,
        "links": [{"type": "tms", "name": case_id, "url": case_id}],
        "statusDetails": {"message": message} if message else {},
        "steps": steps,
    }
    (directory / f"{case_id}-result.json").write_text(json.dumps(result), encoding="utf-8")


def _build_reports(root):
    reports = root / "reports"
    b12 = reports / B12
    _write_txt(
        b12,
        "Web_Ems_Rest_Api_b12_NeoX-03_NXC400_report_2026-10-01_11-22-12_NODE3.txt",
        generated="2026-10-01_11-22-12_NODE3",
        version="03.00.11 (AAVV.221) b12",
        cases=[("EMS1-7001", "test_a", "Pass"), ("EMS1-7002", "test_b", "Pass"), ("EMS1-7003", "test_c", "Fail")],
    )
    (b12 / "Web_Ems_Rest_Api_b12_NeoX-03_NXC400_report_2026-10-01_11-22-12_NODE3_integrated.html").write_text("x", encoding="utf-8")
    _write_txt(
        b12,
        "Web_Ems_Rest_Api_b12_NeoX-03_NXC400_report_2026-10-01_11-22-12_NODE3_judged.txt",
        generated="2026-10-01_11-22-12_NODE3",
        version="03.00.11 (AAVV.221) b12",
        cases=[("EMS1-7001", "test_a", "Pass"), ("EMS1-7002", "test_b", "Pass"), ("EMS1-7003", "test_c", "Fail")],
    )
    allure_b12 = b12 / "allure-results_2026-10-01_11-22-12_NODE3"
    _write_allure(
        allure_b12,
        "EMS1-7002",
        "passed",
        [{"name": "GET /ge/config/12345", "status": "passed"}, {"name": "POST /ge/config", "status": "passed"}],
    )
    _write_allure(allure_b12, "EMS1-7003", "failed", [{"name": "PATCH /nni", "status": "failed"}], "boom")

    b13 = reports / B13
    _write_txt(
        b13,
        "Web_Ems_Rest_Api_b13_NeoX-03_NXC400_report_2026-10-05_09-00-00.txt",
        generated="2026-10-05_09-00-00",
        version="03.00.11 (AAVV.221) b13",
        cases=[
            ("EMS1-7001", "test_a", "Pass"),
            ("EMS1-7002", "test_b", "Fail"),
            ("EMS1-7003", "test_c", "Pass"),
            ("EMS1-7004", "test_d", "Pass"),
        ],
    )
    _write_allure(
        b13 / "allure-results_2026-10-05_09-00-00",
        "EMS1-7002",
        "failed",
        [
            {"name": "GET /ge/config/67890", "status": "passed"},
            {
                "name": "POST /ge/config",
                "status": "failed",
                "statusDetails": {"message": "devKey=abc123 ConnectTimeout host='192.168.128.100'"},
            },
        ],
    )
    _write_allure(b13 / "allure-results_2026-10-05_09-00-00", "EMS1-7003", "passed", [{"name": "PATCH /nni", "status": "passed"}])
    _write_txt(
        b13,
        "Web_Ems_Rest_Api_b13_NeoX-03_NXC400_report_2026-10-05_11-00-00.txt",
        generated="2026-10-05_11-00-00",
        version="03.00.11 (AAVV.221) b13",
        cases=[("EMS1-7002", "test_b", "Pass")],
    )
    _write_txt(
        b13,
        "Web_Ems_Rest_Api_b13_NeoX-03_NXC400_report_2026-10-05_12-00-00.txt",
        generated="2026-10-05_12-00-00",
        version="03.00.11 (AAVV.221) b13",
    )

    summary_dir = reports / "multi_node" / "2026-10-01_11-22-00"
    summary_dir.mkdir(parents=True)
    (summary_dir / "summary.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "node": "NODE3",
                        "summary_line": "1 failed, 2 passed",
                        "report_paths": {
                            "txt_report": "D:\\RestApi auto\\reports\\" + B12
                            + "\\Web_Ems_Rest_Api_b12_NeoX-03_NXC400_report_2026-10-01_11-22-12_NODE3.txt"
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return reports


def test_parse_build_dir_orders_engineering_builds_before_release_and_next_line():
    names = [
        "03.00.12 (AAVV.221) b1",
        "03.00.11 (AAVV.221)C0_redhat",
        "03.00.11 (AAVV.221) b13",
        "03.00.11 (AAVV.221) b2",
        "03.00.11 (AAVV.221) b12_redhat",
    ]
    builds = [rindex.parse_build_dir(name) for name in names]

    assert rindex.parse_build_dir("multi_node") is None
    assert rindex.parse_build_dir("_index") is None
    release = builds[1]
    assert (release.number, release.project, release.build, release.target) == ("03.00.11", "AAVV.221", "C0", "redhat")
    assert (builds[4].build, builds[4].target) == ("b12", "redhat")
    ordered = [build.dir_name for build in sorted(builds, key=rindex.BuildInfo.sort_key)]
    assert ordered == [
        "03.00.11 (AAVV.221) b2",
        "03.00.11 (AAVV.221) b12_redhat",
        "03.00.11 (AAVV.221) b13",
        "03.00.11 (AAVV.221)C0_redhat",
        "03.00.12 (AAVV.221) b1",
    ]


def test_collect_runs_names_nodes_classifies_runs_and_links_companions(tmp_path):
    reports = _build_reports(tmp_path)

    runs = {run.run_id: run for run in rindex.collect_runs(reports)}

    labelled = runs["2026-10-01_11-22-12_NODE3"]
    unlabelled = runs["2026-10-05_09-00-00"]
    judged = runs["2026-10-01_11-22-12_NODE3_judged"]
    assert unlabelled.node == "NODE3"
    assert (labelled.kind, unlabelled.kind) == ("full", "full")
    assert runs["2026-10-05_11-00-00"].kind == "partial"
    assert runs["2026-10-05_12-00-00"].kind == "empty"
    assert labelled.multi_node_summary is not None
    assert labelled.pytest_summary == "1 failed, 2 passed"
    assert judged.tag == "judged"
    assert judged.integrated_path == labelled.integrated_path
    assert judged.allure_dir == labelled.allure_dir


def test_formal_runs_choose_reference_run_and_report_unknown_entries(tmp_path):
    reports = _build_reports(tmp_path)
    formal = tmp_path / "formal_runs.yaml"
    formal.write_text(
        yaml.safe_dump(
            {
                B12: {"NODE3": [{"run": "2026-10-01_11-22-12_NODE3_judged", "final": True, "note": "judged"}]},
                B13: {"NODE3": [{"run": "2026-10-05_99-99-99"}]},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    index = rindex.build_index(reports, formal)

    reference = index.reference_run(B12, "NODE3")
    assert reference.run_id == "2026-10-01_11-22-12_NODE3_judged"
    assert reference.formal == "final"
    header = rindex.render_comparison(index, reference, index.find_run(B13, "NODE3"), [])
    assert "（正式（最終））" in header
    assert "（未標記，暫用最後一次完整執行）" in header
    assert "（final）" not in header
    assert index.reference_run(B13, "NODE3").run_id == "2026-10-05_09-00-00"
    assert any("2026-10-05_99-99-99" in warning for warning in index.warnings)


def test_formal_runs_match_parallel_nodes_sharing_a_timestamp(tmp_path):
    reports = tmp_path / "reports"
    build = reports / "03.00.11 (AAVV.221) b2"
    for chassis, ip, name in (("NeoX-03", "192.0.2.204", "Noex-03_204"), ("NeoX-06", "192.0.2.202", "Noex-06_202")):
        _write_txt(
            build,
            f"Web_Ems_Rest_Api_b2_{chassis}_NXC400_report_2026-05-27_11-46-06.txt",
            generated="2026-05-27_11-46-06",
            version="03.00.11 (AAVV.221) b2",
            cases=[("EMS1-1", "test_a", "Pass")],
            node_ip=ip,
            node_name=name,
        )
    formal = tmp_path / "formal_runs.yaml"
    formal.write_text(
        yaml.safe_dump(
            {
                "03.00.11 (AAVV.221) b2": {
                    "Noex-03_204": [{"run": "2026-05-27_11-46-06", "final": True}],
                    "Noex-06_202": [{"run": "2026-05-27_11-46-06", "final": True}],
                }
            }
        ),
        encoding="utf-8",
    )

    index = rindex.build_index(reports, formal)

    assert index.warnings == []
    assert {run.node: run.formal for run in index.runs} == {"Noex-03_204": "final", "Noex-06_202": "final"}
    selector = "03.00.11 (AAVV.221) b2/2026-05-27_11-46-06"
    try:
        index.find_run(selector, None)
    except ValueError as error:
        assert "add --node" in str(error)
    else:
        raise AssertionError("ambiguous run id must require --node")
    assert index.find_run(selector, "Noex-06_202").node_ip == "192.0.2.202"


def test_compare_runs_classifies_cases_and_names_first_differing_step(tmp_path):
    reports = _build_reports(tmp_path)
    index = rindex.build_index(reports, tmp_path / "missing.yaml")
    before = index.find_run(B12, "NODE3")
    after = index.find_run(B13, "NODE3")

    changes = {change.case_id: change for change in rindex.compare_runs(index, before, after)}

    assert changes["EMS1-7002"].category == "regression"
    assert changes["EMS1-7002"].unstable is True
    assert "POST /ge/config：passed → failed" in changes["EMS1-7002"].step_diff
    assert "ConnectTimeout" in changes["EMS1-7002"].step_diff
    assert "abc123" not in changes["EMS1-7002"].step_diff
    assert "192.168.128.100" not in changes["EMS1-7002"].step_diff
    assert "GET" not in changes["EMS1-7002"].step_diff
    assert changes["EMS1-7003"].category == "fixed"
    assert "PATCH /nni：failed → passed" in changes["EMS1-7003"].step_diff
    assert changes["EMS1-7004"].category == "added"
    assert "EMS1-7001" not in changes


def test_write_index_links_cases_to_integrated_steps_and_keeps_formal_runs(tmp_path):
    reports = _build_reports(tmp_path)
    output = reports / "_index"
    formal = output / "formal_runs.yaml"
    index = rindex.build_index(reports, formal)

    index_path = rindex.write_index(index, output, formal)

    rendered = index_path.read_text(encoding="utf-8")
    assert "Regression 候選" in rendered
    assert "_integrated.html#EMS1-7002" in rendered
    case_pages = sorted(path.name for path in (output / "cases").glob("*.html"))
    assert [name.split("_NODE3_")[0] for name in case_pages] == ["EMS1-7002", "EMS1-7003"]
    assert f'href="cases/{case_pages[0]}">步驟並排</a>' in rendered
    case_page = (output / "cases" / case_pages[0]).read_text(encoding="utf-8")
    assert "POST /ge/config" in case_page
    assert 'href="../../03.00.11%20%28AAVV.221%29%20b12_redhat/' in case_page
    assert "192.168.169.58" not in rendered
    history = (output / "case_history.csv").read_text(encoding="utf-8-sig")
    assert "EMS1-7004" in history
    assert "_NODE3_integrated.html#EMS1-7001" in history
    assert (output / "runs.csv").read_text(encoding="utf-8-sig").count("\n") == 6
    lines = formal.read_text(encoding="utf-8").splitlines()
    start = next(position for position, line in enumerate(lines) if "取消註解" in line) + 1
    suggestions = yaml.safe_load("\n".join(line[2:] for line in lines[start:]))
    assert suggestions[B13]["NODE3"] == [{"run": "2026-10-05_09-00-00", "final": True}]
    assert suggestions[B12]["NODE3"] == [{"run": "2026-10-01_11-22-12_NODE3", "final": True}]

    formal.write_text("# edited by hand\n", encoding="utf-8")
    rindex.write_index(index, output, formal)
    assert formal.read_text(encoding="utf-8") == "# edited by hand\n"


def test_write_index_outside_reports_root_keeps_links_valid(tmp_path):
    reports = _build_reports(tmp_path)
    output = tmp_path / "elsewhere"
    index = rindex.build_index(reports, output / "formal_runs.yaml")

    rendered = rindex.write_index(index, output, output / "formal_runs.yaml").read_text(encoding="utf-8")

    assert 'href="../reports/03.00.11%20%28AAVV.221%29%20b13/' in rendered


def test_main_writes_comparison_page_for_selected_runs(tmp_path, capsys):
    reports = _build_reports(tmp_path)

    exit_code = rindex.main(
        ["--reports-root", str(reports), "--compare", f"{B12}/2026-10-01_11-22-12_NODE3", B13, "--node", "NODE3"]
    )

    assert exit_code == 0
    written = list((reports / "_index").glob("compare_NODE3_*.html"))
    assert len(written) == 1
    assert "EMS1-7002" in written[0].read_text(encoding="utf-8")
    assert "Wrote" in capsys.readouterr().out


def test_main_case_option_writes_single_step_page(tmp_path, capsys):
    reports = _build_reports(tmp_path)

    exit_code = rindex.main(["--reports-root", str(reports), "--compare", B12, B13, "--node", "NODE3", "--case", "EMS1-7002"])

    assert exit_code == 0
    pages = list((reports / "_index" / "cases").glob("EMS1-7002_NODE3_*.html"))
    assert len(pages) == 1
    assert not list((reports / "_index").glob("compare_*.html"))
    assert "Wrote" in capsys.readouterr().out


def test_describe_step_difference_names_the_side_without_allure_result():
    result = {"name": "test_x", "status": "failed", "steps": []}

    assert rindex.describe_step_difference(None, result) == "基準沒有同名的 Allure result（test_x）"
    assert rindex.describe_step_difference(result, None) == "比對沒有同名的 Allure result（test_x）"


def test_redact_text_masks_sensitive_values_in_free_text():
    text = 'devKey=abc123 password: "p@ss" token=xyz other=keep'

    redacted = redact_text(text)

    assert "abc123" not in redacted
    assert "p@ss" not in redacted
    assert "xyz" not in redacted
    assert "other=keep" in redacted
