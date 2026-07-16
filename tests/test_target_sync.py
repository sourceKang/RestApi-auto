from __future__ import annotations

from tests.support.target_sync import LineCardInfo, parse_show_lc_status, update_topology_v2_target_slots


SHOW_LC_ST = """
MSC1240QA# show lc st
48V power: Input-A not exist , Input-B up (DC)
id state    card type                 uptime             f/w version     heat vol fan mon
-- -------- ---------------- ------------------- ----------------------- ---- --- --- ---
1  active   GLC1440X-55                    06:18           V2.03(AAWO.9)   -   -   -   -
2  active   OLC3816-IA                     08:15           V2.03(ACHD.9)   -   -   -   -
3  -                                                                       -   -   -   -
*4  active   MSC1240QA            2 days,17:26:06           V2.03(ABGX.9)   -   -   -   -
MSC1240QA#
"""


def test_parse_show_lc_status_returns_active_cards_only():
    cards = parse_show_lc_status(SHOW_LC_ST)

    assert cards == [
        LineCardInfo(slot_id="1", card="GLC1440X-55", fw_version="V2.03(AAWO.9)", state="active"),
        LineCardInfo(slot_id="2", card="OLC3816-IA", fw_version="V2.03(ACHD.9)", state="active"),
        LineCardInfo(slot_id="4", card="MSC1240QA", fw_version="V2.03(ABGX.9)", state="active"),
    ]


def test_update_topology_v2_target_slots_replaces_stale_controller_and_preserves_service_targets(tmp_path):
    targets = tmp_path / "test_targets.yaml"
    targets.write_text(
        """
nodes:
  NODE1:
    chassis: "IES4204"
    slots:
      3:
        card: "MSC1240QB"
        fw_version: "V2.03(ABGX.8)"
        role: "controller"
      1:
        card: "GLC1440X"
        model: "GLC1440X-55A"
        fw_version: "V2.03(AAWO.8)"
        role: "line"
        ports:
          ge_service: "1"
      2:
        card: "OLC3816"
        model: "OLC3816-IA"
        fw_version: "V2.03(ACHD.8)"
        role: "line"
        ports:
          pon: "1"
        onts:
          primary: "ZTEGC1234567"
    test_targets:
      report_slots: ["3", "1", "2"]
  NODE2:
    chassis: "NeoX-02"
""".lstrip(),
        encoding="utf-8",
    )

    changed = update_topology_v2_target_slots(
        targets,
        "NODE1",
        parse_show_lc_status(SHOW_LC_ST),
        {"MSC1240QA", "MSC1240QB"},
    )

    text = targets.read_text(encoding="utf-8")
    assert changed
    assert '      4:' in text
    assert '        card: "MSC1240QA"' in text
    assert '        fw_version: "V2.03(ABGX.9)"' in text
    assert '        card: "MSC1240QB"' not in text
    assert '        model: "GLC1440X-55A"' not in text
    assert '        card: "GLC1440X-55"' in text
    assert '        card: "OLC3816-IA"' in text
    assert '          ge_service: "1"' in text
    assert '          primary: "ZTEGC1234567"' in text
    assert '      report_slots: ["4", "1", "2"]' in text
    assert '  NODE2:' in text
