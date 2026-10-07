from __future__ import annotations

import json

from tools import case_step_diff as csd


def _write_run(directory, *, host, elapsed, retstatus, alarm_time, status="passed"):
    directory.mkdir(parents=True, exist_ok=True)
    request = {
        "method": "POST",
        "url": f"https://{host}:9116/netatlasemsapi/configNeoXSeries/interface/ge/node/1/39",
        "headers": {"sessionid": "abc-session"},
        "json": {"geservice": {"vlan": 100}, "devKey": "secret-dev-key"},
    }
    response = {"status_code": 200, "elapsed": elapsed, "body": {"retstatus": retstatus, "retval": {"LogTime": alarm_time}}}
    (directory / "req.json").write_text(json.dumps(request), encoding="utf-8")
    (directory / "resp.json").write_text(json.dumps(response), encoding="utf-8")
    result = {
        "name": "test_ge_config",
        "status": status,
        "links": [{"type": "tms", "name": "EMS1-7120"}],
        "steps": [
            {"name": "GET /ge/config/12345", "status": "passed", "attachments": []},
            {
                "name": "POST /configNeoXSeries/interface/ge",
                "status": status,
                "statusDetails": {"message": f"ConnectTimeout host='{host}'"} if status != "passed" else {},
                "attachments": [
                    {"name": "request 1a2b", "source": "req.json", "type": "application/json"},
                    {"name": "response 1a2b", "source": "resp.json", "type": "application/json"},
                ],
            },
        ],
    }
    (directory / "r-result.json").write_text(json.dumps(result), encoding="utf-8")
    return directory


def test_diff_values_marks_timing_and_alarm_fields_as_volatile():
    before = {"elapsed": 1.2, "body": {"retstatus": "Success", "retval": {"LogTime": "10:00", "LogID": 7, "Name": "a"}}}
    after = {"elapsed": 3.4, "body": {"retstatus": "Fail", "retval": {"LogTime": "11:00", "LogID": 8, "Name": "a"}}}

    diffs = {diff.path: diff.volatile for diff in csd.diff_values(before, after)}

    assert diffs == {
        "elapsed": True,
        "body.retstatus": False,
        "body.retval.LogTime": True,
        "body.retval.LogID": True,
    }


def test_normalize_attachment_ignores_ems_host_in_request_url():
    request = {"method": "GET", "url": "https://192.168.128.100:9116/netatlasemsapi/device"}

    assert csd.normalize_attachment("request", request)["url"] == "/netatlasemsapi/device"
    assert request["url"].startswith("https://")


def test_compare_result_steps_flags_step_with_changed_response_body(tmp_path):
    before_dir = _write_run(tmp_path / "a", host="192.168.128.8", elapsed=1.0, retstatus="Success", alarm_time="t1")
    after_dir = _write_run(tmp_path / "b", host="192.168.128.100", elapsed=2.0, retstatus="Fail", alarm_time="t2")
    before = csd.load_case_results(before_dir)["EMS1-7120"][0]
    after = csd.load_case_results(after_dir)["EMS1-7120"][0]

    steps = {" › ".join(step.path): step for step in csd.compare_result_steps(before, after, before_dir, after_dir)}

    assert steps["GET /ge/config/#"].changed is False
    post = steps["POST /configNeoXSeries/interface/ge"]
    assert post.changed is True
    request, response = post.attachments
    assert (request.kind, request.diffs) == ("request", [])
    assert [diff.path for diff in response.substantive] == ["body.retstatus"]
    assert {diff.path for diff in response.diffs if diff.volatile} == {"elapsed", "body.retval.LogTime"}


def test_render_case_comparison_shows_side_by_side_without_secrets_or_ip(tmp_path):
    before_dir = _write_run(tmp_path / "a", host="192.168.128.8", elapsed=1.0, retstatus="Success", alarm_time="t1")
    after_dir = _write_run(
        tmp_path / "b", host="192.168.128.100", elapsed=2.0, retstatus="Fail", alarm_time="t2", status="broken"
    )

    rendered = csd.render_case_comparison("EMS1-7120", "b12 / run1", "b13 / run2", before_dir, after_dir, "a.html", "b.html")

    assert "body.retstatus" in rendered
    assert "可能為動態值" in rendered
    assert "passed → broken" in rendered
    assert "ConnectTimeout" in rendered
    assert "192.168.128" not in rendered
    assert "abc-session" not in rendered
    assert "secret-dev-key" not in rendered
    assert '<details class="step changed" open>' in rendered
    assert '<details class="step"><summary><span>GET /ge/config/#' in rendered


def test_render_step_pair_summarizes_attachment_present_on_one_side_only():
    step = {"name": "POST /x", "status": "passed", "attachments": []}
    pair = csd.StepPair(("POST /x",), None, step, [csd.AttachmentPair("request", csd._MISSING, {"url": "/x"})])

    rendered = csd.render_step_pair(pair)

    assert "<td>(整個附件)</td><td>(無)</td><td>有，見下方</td>" in rendered
    assert '<details class="step changed" open>' in rendered


def test_render_case_comparison_without_allure_explains_missing_data():
    rendered = csd.render_case_comparison("EMS1-1", "a", "b", None, None, "a.html", "b.html")

    assert "沒有 Allure 原始資料" in rendered
