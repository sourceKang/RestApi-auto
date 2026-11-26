# 共用工作進度

更新日期：2026-11-16（Asia/Taipei）。此檔是交接快照；
接手時先核對 Git 與現有檔案，不能把本文當作即時設備狀態或測試通過證據。

## 雙工具協作設定

- 負責工具：Claude Code（2026-09-22 起）；先前由 Codex 建立共用協作入口。
- 分支：每個任務從 codex/prepare-github-upload（GitHub 預設分支）切出 `claude/<topic>` 或
  `codex/<topic>`。合併前先在 scratch worktree 做 `git merge --no-commit --no-ff` dry run，
  零衝突才開 PR，由使用者審閱後合併。
- 共用 skill 以 .codex/skills/<name>/SKILL.md 為來源（qa-bug-report、ems-version-regression），
  Claude 側 .claude/skills/<name>/SKILL.md 只轉介，未複製業務規則。
- 未新增全域權限設定、MCP 憑證或設備操作自動化。
- Repo 公開性：專案負責人已明確決定維持 Public（帳密皆為 per-person 環境變數），不需要轉 Private。

## 最近一次工作

較早的紀錄見 docs/work-history/（依月份）。

### 2026-11-20 b17 NODE1 回歸（Claude Code）

- 分支 claude/b15-regression（HEAD c7d5673），未提交。TestLink build `03.00.11 (AAVV.221) b17` 已存在（id 21026，
  2026-11-20 10:35 建立），未重建。
- 使用者表示 .8 已升 b17；configs/ems.yaml ubuntu version 改為 b17（URL 維持 IPv6 `[2001:2:128::8]`），redhat 不動。
- OpenAPI guard local 12 通過／3 skip、live 15 通過（spec 資料夾無新檔）；dry-run 指令與 b16 相同。
- NODE1 回歸 reports/multi_node/2026-11-20_11-12-10：pytest 222 passed／91 skipped／3 errors，Complete 316/316，22m36s。
- 3 筆失敗皆 RAD 外部帳號 EMS1-7056／7107／7108 登入回 `Invalid username.`，與同日 b16 IPv6 輪相同（b16 時已確認
  IPv4 也一樣）；與 b16 正式輪（11-16）比對：Regression 候選僅此 3 筆、已修復 0、其他無差異。
  比對報表 reports/_index/compare_NODE1_b16_ubuntu_vs_b17_ubuntu_34ce3667ef.html。原因未確認（推測 RADIUS 設定或連線）。
- 未做：formal_runs.yaml 標記、TestLink b17 回填（需使用者確認預覽）、RAD 原因調查、NODE3。

### 2026-11-16 b16 TestLink build（Claude Code）

- 依使用者指示建立 TestLink build `03.00.11 (AAVV.221) b16`（id 20992，NetAtlasEMS／NetAtlas EMS，
  release date 2026-11-16），readback 驗證成功。
- 使用者表示 b16 已升級；configs/ems.yaml ubuntu（.8）改為 b16（redhat 維持 b15，未確認 .100 是否升版），未提交。
- NODE3 `show lc st`：slot 1／3／4 皆 V1.03 b9，已把 test_targets.local.yaml 的 b8 改為 b9；NODE1 卡版本與設定一致。
- OpenAPI guard local 12 通過／3 skip、live 15 通過；dry-run（--nodes NODE1,NODE3 --run-full-testcases）正常。
- b15 bug #263239、#263277 已 Released（#263239 Fix Version b16；#263277 未填 Fix Version），待 b16 驗證。
- NODE1 回歸 2026-11-16_10-31-58（run_multi_node，使用者要求只跑 NODE1，NODE1 結束後停止 runner，NODE3 未跑）：
  pytest 225 passed／91 skipped／0 failed，txt 173 Pass／0 Fail，Complete 316/316；與 b15 正式輪比對 Regression 0、
  已修復 4（EMS1-6675／6676／6677／7109）。已記入 reports/_index/formal_runs.yaml。
- TestLink b16 回填 NODE1（使用者確認預覽後寫入）：operation `b16-ubuntu-node1-20261116`，173 筆 p、0 錯誤、81 Skip 忽略；
  抽查 6640／6643／6675／7109 readback 皆 p。之後 NODE3 回填時共同 case 會在同 build 多一筆 execution。
- #263239 驗證：NODE1 2-16-1 UnReg 5 分鐘內 10 次 4 個 GET 全 200（b15 為 500），重新註冊後 IS 且 200 → b16 已修。
  log 在 reports/03.00.11 (AAVV.221) b16_ubuntu/b16_bugverify/。
- #263277 驗證：repro_valid_session_errors.py 3 次（各 540 秒，11:02～11:29）共 4367 筆全部 Success（b15 約 0.5～6% 錯誤），
  搭配 NODE1 回歸無此類錯誤，判定 b16 未再重現；log 同上目錄。
- NODE3 回歸 2026-11-16_11-31-22（--nodes NODE3 --run-full-testcases）：pytest 314 passed／2 failed（1:36:53），
  txt 252 Pass／2 Fail。與 b15 正式輪比對：Regression 1（EMS1-7119）、持續問題 1（EMS1-7223）、已修復 1（EMS1-7173）。
  - EMS1-7119 GE 1/39 POST 回 `This card is not NXA card`，但 `show lc st` slot 1 NXA340 active（uptime 4 天）；
    單獨重跑 7119＋GE error case 2/2 通過 → 偶發，未開單，待再觀察。
  - EMS1-7223 cleanup 等待 ONT 3-16-1 回 IS 逾時（CLI 仍 UnReg）；事後 REST GET 顯示 ONT 已 IS，不需還原設備。
- 單獨重跑（log：reports/03.00.11 (AAVV.221) b16_ubuntu/b16_failrerun/）：7119 共 4 次全通過（偶發）。
  7223 重跑仍失敗；CLI 唯讀監看（每 ~37 秒，13:36 起）顯示：13:32:45 restore POST 回 Success 後，
  13:36:15～13:45:27 running-config 都沒有 `interface remote xont 3-16-1`、ONT 在 unreg 清單；teardown 13:46:04
  送同樣 POST 後，13:46:04 CLI 即出現設定（OOS-NR），13:46:42 IS。→ 第一次 POST 回 Success 但設備沒有設定，
  偏向 EMS 沒下發；13:32:45～13:36:15 無 CLI 樣本，無法排除「下發後又被 EMS 移除」。尚未開單。
  第二次重跑（全程 CLI 監看，每 ~17 秒）通過：14:03:11 DELETE ontservice＋ONT config，14:03:43 restore POST，
  14:03:58 CLI 出現設定（OOS-NR）、14:04:14 IS。失敗的 3 次 restore POST 都在 DELETE 後約 11 秒送出，
  通過這次隔 32 秒 → 推測與 DELETE 後太快重建有關（未證實；run1 teardown 隔 12 秒也成功，但當時 ontservice 早已刪除）。偶發，尚未開單。
- 14:28～15:03 重驗 b15 bug：#263239 UnReg 期間 60 次 GET 全 200、重新註冊後 IS（與上午一致，已修）；
  #263277 3 輪全 Success（與上午一致，未再重現）。
- NODE3 第二輪完整回歸 2026-11-16_15-03-21（全程 CLI 監看 204 筆，log 在 b16_node3_cli_watch/）：
  316 passed／0 failed，txt 254 Pass／0 Fail；7119、7223、7173 皆 Pass。slot 1 全程 active NXA340。
  7223 這輪 restore POST 在 DELETE 後 33 秒送出，15:36:15 CLI OOS-NR、15:36:39 IS → 再次支持「DELETE 後約 11 秒就重建才失敗」的推測（未證實）。
- TestLink NODE3 預覽改用第二輪：`b16-ubuntu-node3-20261116-r2`（digest e60707ae…），254 筆全 p，逐筆核對一致，尚未寫入；
  第一輪預覽 `b16-ubuntu-node3-20261116` 作廢不寫。
- TestLink b16 回填 NODE3 r2（使用者確認後寫入）：254 筆 p、0 錯誤；readback 6640／7119／7173／7223 皆 p。
- 7223 時間差驗證（使用者同意改動 NODE3；腳本 b16_failrerun/test_probe_7223_timing.py，CLI 監看 probe_cli_watch/，
  每輪：套 SFU template → 刪 ontservice → DELETE ONT config → 約 12 秒後 POST 重建 → 觀察 10 分鐘 → 未恢復則還原）：
  3 輪中 2 輪重現（R1 17:18、R3 17:48）：CLI 在 POST 後約 0～5 秒出現 `interface remote xont 3-16-1`（OOS-NR），
  約 15～19 秒後設定從設備消失、ONT 進 unreg，期間腳本只送 GET；R2 間隔相同但設定留下並 IS。
  另觀察到刪 ontservice 時 EMS 會自行移除設備上的 ONT 設定（R2 17:38:52 早於腳本 DELETE）。
  → 「間隔短必失敗」不成立；現象是偶發的「下發後被移除」，推測為 ontservice 刪除的背景處理延遲清掉重建的設定（未證實，無 EMS 端 log）。
  每輪結束 ONT 皆已還原 IS。尚未開單。
- 2026-11-18 7223 單獨重跑（全程 CLI 監看，b16_failrerun/7223_run3*）：Pass（10:15）。09:26:36 刪 ontservice＋ONT config，
  09:27:09 restore POST（隔 33 秒），09:27:20 CLI 出現設定、09:27:34 IS 並維持。累計 7223 正式 case 6 次：3 Fail／3 Pass；
  通過的 3 次 restore 間隔都約 32～33 秒，失敗的都約 11～15 秒（時間差腳本已證明短間隔不必然失敗）。
- 2026-11-18 7223 間隔 A/B（b16_failrerun/test_probe_7223_gap_ab.py，CLI 判定，probe_ab_cli_watch/）：
  12 秒組 3 輪 1 removed（R1：09:47:43 POST，09:47:50 設定出現，09:48:07 消失）、2 kept；35 秒組 3 輪全 kept。
  合計 12 秒 6 輪 3 removed，35 秒（含 testcase 32～33 秒）6 次 0 失敗 → 短間隔是必要條件、非充分條件（樣本小，未證實）。
  另觀察：被移除的 3 輪，REST 反映 template 套用都花 3.5～4 分鐘；kept 的多為 1～3 分鐘（僅觀察）。ONT 已還原 IS。
- 2026-11-18 7223 清理順序 B（先 DELETE ONT config、等 CLI 清除＋UnReg，再刪 ontservice，12 秒後 POST；
  b16_failrerun/test_probe_7223_order_b.py，probe_b_cli_watch/）：第一次 10:55 跑到第 5 輪時 session 中斷（11:27），
  ONT 停在無設定／UnReg、ontservice 已刪；16:26 以 DELETE→等 35 秒→POST 還原，16:27:12 CLI IS。
  前 4 輪：R1 removed（10:57:57 POST，10:58:04 出現，10:58:22 消失），R2～R4 kept → 對調順序不能消除問題。
  16:27 起補跑剩下 2 輪：R5 removed（16:34:53 刪 ontservice，16:35:07 POST，16:35:14 出現、16:35:26 IS、16:35:31 消失），
  R6 kept（16:42:31 POST，16:42:56 IS）。B 順序合計 6 輪 2 removed／4 kept → 對調順序不能消除；
  R5 在 IS 之後才被移除，排除「ONT 沒註冊上」。結束時 ONT IS。結論：刪 ontservice 觸發的 EMS 背景清理與重建競態，
  測試需在 POST 前等 EMS 清理完成（待確認可用訊號，需問 RD）。
- 使用者判定 7223 不開 bug：NeoX config API 先移除再下設定屬預期行為，問題是測試清理在 ontservice 刪除的背景操作完成前就重建。
  修改計畫（重建後 CLI 確認 60 秒、被移除則重送最多 2 次，僅 7223 啟用）尚待使用者確認，程式未改。
- EMS .8 REST API 背景 command log：依 Notion 頁面需 conf/RESTAPIDebugLevel.conf 設 10、看 logs/RESTAPILog.log；
  .8 執行目錄 /opt/ELEMENTVIEW_MASTER/conf 無此檔，只在 /opt/ems_deploy/ems_master/conf 有 debugLevel=0，log 只有 WARN。
  2026-11-18 已寄信詢問 RD Leaf Yeh 正確步驟（使用者同意），等回覆；.8 設定未改。SSH 用 EMS web auto 的 scripts/ssh_run.py。
- 2026-11-20 使用者要求 EMS 改 IPv6：configs/ems.yaml ubuntu rest_api_url 改為 `https://[2001:2:128::8]:9116/netatlasemsapi`（未提交）；
  本機 IPv6 ping／TCP 9116 通，登入／GET／登出 200。NODE1 完整回歸 2026-11-20_09-03-09：170 Pass／3 Fail（22 分）；
  與 11/16 IPv4 比對只有 EMS1-7056／7107／7108（RAD external）Regression，回 `Invalid username.`；
  同時以 IPv4 URL 登入 RAD readwrite／readonly 也失敗 → 非 IPv6 問題，RAD 外部帳號在 11/16 之後失效（類似 10 月 .100 升級後現象），原因未確認。
  其餘 case 結果與 IPv4 相同。未回填 TestLink。注意：比對工具步驟正規化只遮 IPv4，IPv6 URL 會被當成步驟差異。
- Leaf 11/20 回覆：RESTAPIDebugLevel.conf 已停用，改由 /opt/ELEMENTVIEW_MASTER/conf/log4j2_ems.xml 的
  `<Logger name="RESTAPILogger" level="info">` 控制（0→info、1..6→debug、7+→trace），存檔後 10 秒內生效、不需重啟。
  .8 目前 RESTAPILogger=info；log4j2_ems.xml、lib、mibs 時間戳為 2026-11-19 21:16 → .8 EMS 在 11/19 晚上重新安裝／升級，
  版本檔 version.conf 為空，實際 build 未確認（ems.yaml 仍寫 b16）。RAD 失效可能與此有關，未確認。
- 2026-11-20 15:24 使用者同意：.8 log4j2_ems.xml 第 507 行 RESTAPILogger info→trace（備份
  /opt/ELEMENTVIEW_MASTER/conf/log4j2_ems.xml.bak-20261120-restapi-trace，diff 只差這行）；15:25 起 RESTAPILog.log 印出
  [RequestLog]（時間為 UTC）。**測完必須改回 info**。15:27 起跑 7223 時間差腳本（舊順序 12 秒 ×4，probe_trace_*）。
- trace 第 1 輪（15:30）結果 never（CLI 15:30:50 起無設定；POST 15:30:43 完成，CLI 樣本有 8 秒空檔）。RESTAPILog 顯示：
  DELETE /ontservice 11 ms、**不送任何 SSH command**；DELETE config → `no interface remote xont 3-16-1`；POST → 先
  `no interface remote xont 3-16-1` 再 `config / interface remote xont 3-16-1 / sn / registration-id / register-method A /
  description / type auto / adminstate enable / exit`；之後到 15:31:30 沒有其他 REST API 對此 ONT 的 command。
  → 刪設定的不是 REST API 模組。WebAutoProvision.log 每 30 秒跑一次 CheckProfile（07:30:09、:39、07:31:09…），
  logger 為 info，看不到它下的 command；推測 ontservice 刪除由此 30 秒週期工作處理（與「12 秒間隔約一半失敗、35 秒以上不失敗」吻合），未證實。
  另：WebAutoProvision 每 30 秒都 `[CheckProfile] exception NullPointerException: Cannot read field "Status"`（今天已 2715 次）。
- **7223 根因已確認（trace 第 2 輪，15:40）**：`DELETE /ontservice/{sn}` 只把 DB ServiceInfo 標成 state='Delete'（17 ms，
  不送 command）；WebAutoProvision **Thread-0 每 30 秒**查 `state='Delete'`，07:40:50.519Z 找到後對 NODE3 送
  **SNMP SET `NEOX06-MIB:xontRowStatus.30016.1`**（刪掉 xont 3-16-1），再 `DELETE FROM ServiceInfo`。
  我們的 restore POST 在 07:40:50.43Z 剛下完設定，0.18 秒後就被這個 SNMP SET 刪掉 → CLI 15:40:54 起 UnReg。
  所以刪 ontservice 後設備端清理會在下一個 Thread-0 週期（≤30 秒）才執行；間隔 ≥35 秒的重建都在週期之後，故不受影響。
  不是 CLI command，所以 CLI／RESTAPILog 都看不到。
- 15:46:15 已把 RESTAPILogger、WebAutoProvision 改回 info；與備份 diff 一致、sha256 相同（備份檔仍留在 .8 conf/）。
  trace 第 3、4 輪在改回後繼續跑（無 trace），結果不再用於分析。
- 7223 修正（使用者同意計畫，分支 `claude/7223-wait-autoprov-delete`，未提交）：
  - `ProvisionService.delete_ont_service_if_uses_template` 改回傳是否真的刪除（bool）。
  - `cleanup_ont_provision_template_scenario`：有刪 ontservice 時不再 REST DELETE ONT config，改以 CLI 等
    `interface remote xont` 消失（WebAutoProvision 移除，timeout 120 s、interval 5 s，allure 記錄等待秒數），逾時判 Fail；
    沒刪 ontservice 時維持原本 DELETE＋等待。
  - 離線測試：新增 3 筆（等待 EMS 移除、未刪時照舊、EMS 未移除判 Fail），服務層測試加回傳值斷言；
    `pytest -m offline` 211 passed；相關檔案 46 passed；compile OK。
  - 實機驗證：NODE3 單獨跑 7223 ×3（fix_verify_*），排在時間差腳本結束後執行。
- 實機驗證第 1 次（16:00，報表在 b17_ubuntu）：Pass（641 s）。16:05:08 DELETE ontservice → 等 EMS 移除 23.1 s
  （CLI 16:05:28 設定消失）→ 16:05:37 POST 基準 → 16:05:42 OOS-NR、16:05:57 IS，之後 25 筆樣本穩定。
- 實機驗證第 2、3 次也 Pass：第 2 次（725 s）16:15:21 刪 ontservice → 等 13.8 s → 16:15:41 POST → 16:16:06 IS，
  之後 36 筆穩定；第 3 次（620 s）16:27:22 → 等 13.8 s → 16:27:42 POST → 16:27:58 IS，之後 24 筆穩定。
  合計 3/3 Pass，重建後設定皆未被刪（fix_verify_cli_watch/）。結束時 ONT IS。
- **版本**：configs/ems.yaml 的 ubuntu version 在 2026-11-20 11:11:12 被改成 b17（非本 session 所改），
  11:11～11:12 有其他 b17 報表。.8 在 11/19 21:16 重裝，故 09:03 的 IPv6 NODE1 回歸實際可能是 b17，
  卻標成 b16、放在 b16_ubuntu 並記入 formal_runs b16（待更正）。
- 2026-11-20 使用者要求：09:03 IPv6 NODE1 那輪改標 b17：報表 3 檔＋allure 目錄由 b16_ubuntu 移到 b17_ubuntu，
  檔名與內文 `(AAVV.221) b16`→`b17`（txt 1 處、html 8、integrated 7、allure 附件 1）；formal_runs 移到新增的
  `b17_ubuntu` 下（final: false）；index 重建。17:45 起在分支 claude/7223-wait-autoprov-delete 跑 NODE1→NODE3 完整回歸
  （b17、IPv6，NODE3 期間 CLI 監看 b17_ubuntu/node3_cli_watch/）。
- b17 回歸結果（2026-11-20_17-45-01，19:48 結束）：
  - NODE1 2026-11-20_17-45-04：173 Pass／0 Fail，RAD external 恢復 Pass，與 b16 正式輪比對 Regression 0。
  - NODE3 2026-11-20_18-06-50：230 Pass／10 Fail／14 Skip。比對 b16 正式輪 Regression 10。根因：EMS 現以 IPv6
    `2001:2:169:0:fad4:a3ff:fec9:e1b0` 納管 NODE3，但 test_targets.local.yaml 的 device_ip 是 192.168.169.58；
    device／slot 的 IPAddress 比對、GE port 與 ONT readiness（比對 IP）、geservice 以 IP 過濾都失敗，連帶 ONT／ontservice
    與 RAD 共 14 筆 skip，7109 summary Fail。7223（修正後）、7119、7173 Pass。非 API bug，屬環境／設定不一致。
- 2026-11-24 IPv4／IPv6 雙測修正（使用者同意設計，分支 `claude/ipv4-ipv6-targets`，自 base 開，未提交）：
  ems.yaml `ubuntu`=IPv4、新增 `ubuntu_ipv6`；node 新增 `device_ip_v6`、`managed_ip_family`（`EMS_NODE_IP_FAMILY` 單次覆寫），
  `dut.device_ip` 指向納管位址、`device_ip_v4` 保留 IPv4、ssh_host 仍 IPv4；device preflight 比對 EMS IPAddress，
  不符即停並列修正方式；報表加 `Node IP Family`；step 比對遮 IPv6；remote console inband 改比 IPv4；ADR 0003、project-context。
  本機 test_targets.local.yaml NODE3 設 ipv6（不提交）。離線：新測 12 passed、`-m offline` 223 passed；
  test_hardware_config 的 firmware 版本失敗為既有本機設定問題（無本次修改也失敗）。
  實機驗證 10:10 起：NODE1 走 ubuntu（IPv4），接著 NODE3 走 ubuntu_ipv6（納管 IPv6）＋CLI 監看。
  注意此分支不含 7223 修正（PR #41），7223 可能偶發失敗。
  10:29 使用者要求停止（NODE1 環境需調整）：NODE1 跑到 95%（267+/316，4 Fail＝EMS1-6644／6680 rw＋ro，slot 1 卡被換成
  GLC1540X-55A V2.03(ACFF.10)b1，uptime 約 30 分），runner／pytest 已全部停止，未產生報表；NODE3 未開始。
  中斷在 session 測試，session 範圍 fixture 的收尾（例如 seed 的 ONT／GE service）可能沒跑到，下次開跑前留意。
  使用者確認 .8 目前為 b17（ems.yaml 已是 b17）。
- NODE1 環境調整後 CLI 唯讀檢查（2026-11-24）：卡 MSC1240QA V2.03(ABGX.10)b1、GLC1540X-55A V2.03(ACFF.10)b1、
  OLC3816-IA V2.03(ACHD.10)b1（約 35 分前重開）；inband 192.168.169.57；ONT 2-16-1 無設定、在 unreg 清單；GE 1-39 status disable。
  依使用者指示更新：test_targets.local.yaml NODE1 三張卡（本機、不提交）；hardware_matrix.yaml 三張卡加 `versions`
  （保留 .9、加 .10 b1），IES4204 report_card_order／line_cards／ge_service_cards 加 GLC1540X-55A（未提交）。
  config secrets 0；offline 222 passed／1 failed（test_default_topology_v2_node1…：讀到本機檔，仍預期 GLC1440X-55）；
  test_node1_report_cards_are_yaml_targeted 同因失敗；committed test_targets.yaml NODE1 仍是 GLC1440X-55／.9（待使用者決定）。
- 2026-11-24 使用者選擇兩邊一起改：committed test_targets.yaml NODE1 改 GLC1540X-55A／.10b1，兩個測試預期值同步；offline 223 passed。
- IPv4／IPv6 實機驗證第 2 次（13:39 起，reports/ipv6_verify_progress_2026-11-24_r2.txt）：
  - NODE1（ubuntu）2026-11-24_13-39-08：173 Pass／0 Fail；報表 `Node IP Family: ipv4`、三張卡為 .10b1。
  - NODE3（ubuntu_ipv6）2026-11-24_13-59-43：14:51 app 重啟時 runner 被中止，未產生報表；中止前 86 Pass／6 Skip／0 Fail。
    之前 b17 的 10 Fail（IPAddress、GE／ONT readiness、geservice by IP）都已通過，preflight 通過。
  - 6 筆 alarm skip：KeyWord 用 IPv6 查 `/activealarm` 得 No data。11/20 同一 alarm 的 DevIP 是 192.168.169.58（trap 來源 IPv4）。
    依使用者同意修正：`services/alarm/service.py` 新增 `alarm_source_ip()`（device_ip_v4 優先），KeyWord／DevIP／inband 都用它；
    test_alarm 加 2 筆離線測試；ADR 0003 加說明。offline 223 passed；尚未實機驗證。
  - 14:36:15 DELETE ontservice → 14:36:28 POST ONT config → 14:36:53 CLI 設定消失（7223 同型，此分支無 PR #41 修正），
    之後測試輪詢 /ont/sn 等 ONT 上線直到中止。
  - 使用者同意後：本分支 merge claude/7223-wait-autoprov-delete（951ff5d，未 push）；16:13 以
    reports/…b17_ubuntu_ipv6/restore/test_restore_node3_ont.py 恢復 3-16-1（無 ontservice → POST → 16:13:47 CLI 有設定且 IS）。
    16:14 起 NODE3 第 3 次（ubuntu_ipv6，CLI 監看 node3_cli_watch_r3，進度 reports/ipv6_verify_progress_2026-11-24_r3.txt）。
  - NODE3 第 3 次結果 2026-11-24_16-14-01（17:42 結束）：報表 223 Pass／4 Fail（pytest 278 passed／4 failed／34 skipped）；
    報表 `Node IP: 2001:2:169:0:fad4:a3ff:fec9:e1b0`、`Node IP Family: ipv6` 正確。7223 收尾未再刪掉 ONT 設定。
    - alarm 6 筆仍 skip，IPv4 KeyWord 也查不到 → 「DevIP 是 IPv4」的推測不成立，已還原（alarm 仍用 device_ip）。
      唯讀查證：EMS 中 NODE3 的 alarm（11/22 Device Not Responding／Responding）DevIP 皆為 IPv6；
      CLI `show snmp` trap destination 只有 IPv4（192.168.128.8、.100、1.2.3.4），Login Success trap 未被 EMS 記錄。
      需使用者決定是否在 NODE3 加 IPv6 trap destination（設備設定變更）。ADR 0003 已改為此結論。
    - EMS1-6838／6917：POST ONTServiceProfile 回 `Reach the maximum number of profiles 3000 in database.`；
      唯讀計數 2997 筆，其中 2671 筆 `Auto_max*`（非本專案建立）。環境問題，清理需使用者／擁有者決定。
    - EMS1-6666（16:14）：ontservice 建在 ONT 2（預期 1）；CLI 見 3-16-1 基準設定與 service 設定並存。
      16:13 剛恢復基準設定 1 分鐘即開跑，推測 EMS 尚未同步（未證實）。
    - EMS1-7131（16:39）：POST ONT config 回 `This card is not NXP card`；第 2 次（14:27）同 case Pass，原因未查明，待單獨重跑。
  - 2026-11-26 使用者同意：NODE3 CLI `snmp-server trap-destination 4 address 2001:2:128::8 udp-port 162 version v2c`
    （只改 running-config，未 write memory；還原＝改回 0.0.0.0）。11:15:53 REST remote console 後 EMS 收到 Login Success，
    DevIP=2001:2:169:0:fad4:a3ff:fec9:e1b0 → 確認 alarm 需 IPv6 trap destination。11:16 起單獨重跑 test_alarm、test_provision、
    7131（log／CLI 監看在 reports/…b17_ubuntu_ipv6/rerun_2026-11-26*）。
    結果 11:24：40 passed／0 failed（alarm 7 筆含 lifecycle、provision 含 6666、7131 全 Pass）。
    6666 這次建在 ONT 1，支持「上次是恢復後立即開跑、EMS 未同步」的推測；7131 的 `not NXP card` 未重現（原因仍未查明）。
  - 2026-11-26 NODE3 完整回歸 r4（ubuntu_ipv6，含 PR #41 修正 merge 951ff5d，trap destination 4 已設 IPv6）：
    報表 2026-11-26_11-28-12_NODE3，247 Pass／2 Fail（pytest 309 passed／2 failed／5 skipped），1:30:09。
    標頭 `Node IP: 2001:2:169:0:fad4:a3ff:fec9:e1b0`、`Node IP Family: ipv6`、`EMS Target: ubuntu_ipv6`。
    失敗僅 6838／6917（已知環境問題：profile 上限 3000）；5 個 Skip（6836／6837／6839／6840／6918）皆因同一 profile 建立失敗。
    alarm lifecycle、6666、7131、7223 皆 Pass；CLI 監看（node3_cli_watch_r4）結束時 ONT 3-16-1 基準設定在且 IS。
  - 2026-11-26 使用者同意清理 Auto_max* ONTServiceProfile：唯讀盤點 2671 筆（內容相同，無 ONTTemplateProfile
    的 serviceprof1..32 引用；`GET /ontservice` 回 500 未能查），逐筆備份於 reports/…b17_ubuntu_ipv6/cleanup/automax_backup.json。
    14:08 試刪 10 筆全 Success 且 GET 確認已消失（delete_log.txt），總數 2997→2987。
    使用者要求先不刪其餘 2661 筆；單獨重跑 6838／6917／6836／6837／6839／6840／6918：7 passed／0 failed，
    跑完總數仍 2987（測試建立的 profile 有刪回）。另 ONTTemplateProfile 有 2867 筆 Auto_max*（共 2944），接近 3000 上限，未處理。
    仍待：其餘 2661 筆 Auto_max* 是否刪除；trap destination 是否 write memory。
  - 2026-11-26 IPv4／IPv6 變更提交 2faff58，開 PR #42（base codex/prepare-github-upload，含 PR #41 的 52bae0b）。
    offline 223 passed。之後依使用者要求把 NODE3 韌體 V1.03(ACKG/ACKI/ACQE.0)b9 加入 hardware_matrix 的 versions
    並更新 test_targets.yaml NODE3（NODE5／7／8 仍為 V1.02，兩版並列）；NODE1 已是 .10b1、無 V1.03。
    offline 223 passed，相關測試在本機與 committed targets 下皆 31 passed。
  - 2026-11-26 使用者要求合併：PR #41 dry run 衝突 0 → 合併 2074fc4；PR #42 對更新後的 base dry run 衝突 0（19 檔）
    → 合併 6de312c（codex/prepare-github-upload）。兩者合併前 CI 皆 pass。
- 未做：確認 ems.yaml 改 b17 是誰改的；7223 修正 push／PR（已在分支 claude/7223-wait-autoprov-delete 提交 52bae0b，未 push）；RAD external 失效原因（需確認 .8 的 RADIUS 設定或 RADIUS server）；7223 測試修改（待 Leaf 回覆／使用者確認計畫）；Redmine 驗證留言（需使用者確認預覽）；b16_redhat build 未建。

### 2026-11-10～11 b15 第 4 輪、NODE1 重跑與開 bug（Claude Code）

- 分支 claude/b15-regression（基準 c7d5673）；configs/ems.yaml b15 與本檔仍未提交。
- R4 2026-11-10_11-19-01：NODE1 通過 186／失敗 7＋1 error；NODE3 通過 314／失敗 2。
- EMS1-6666（ont_service_by_sn 停在 Wait）判定為環境問題，不開 bug：ONT 實體線鬆脫（使用者重插），且 2-16-1 被另一台
  ONT（SN ZYXEC601D0A6）的設定佔用，POST 分到 ONT 2。經使用者同意刪除 2-16-1、把 ZYXEC601D0A6 重建在 2-16-2 後，
  6666–6669 通過 7／失敗 0。測試沒有先確認 ONT 存在（框架改善項目）。
- NODE1 完整重跑 2026-11-10_15-15-28：通過 219／失敗 6／skipped 91；6 個失敗都是 EMS1-6675／6676／6677
  （兩種角色）GET /ont 回 HTTP 500。完整重現（16:56–17:05）與 RD 腳本 `--toggle`（17:28–17:36）都證實：PON 上有未註冊
  ONT 時回 500，註冊回來後恢復 200。最後 CLI：2-16-1 IS（ZYXE8CADDDC3）、2-16-2 IS（ZYXEC601D0A6）、unreg 清單為空。
- Redmine（使用者確認預覽後建立）：
  - #263239 GET /ont 在 PON 上有未註冊 ONT 時回 HTTP 500（EMS1-6675，L2）；已被指派。腳本 rd_repro_ont_unreg_500.py
    在 b15_evidence_2026-11-06/；11-11 讀回時附件數為 0，使用者表示已附，待再確認。
  - #263277 有效 session 偶發 HTTP 500／no privilege／No data found（EMS1-6643，Regression，L2）；附 repro_valid_session_errors.py。
    由 NODE3 session（11-11 以 NeoX 重現）合併原草稿 1 與 No data found 草稿。
- 未開單：EMS1-7223（R4 NODE3，restore POST 回 Success 但設定沒套用），只發生一次，重現需改動 NODE3，待使用者同意。
  NODE3 R2 的 4 個 not-NX-card 之後未再出現，未開單；session 600 秒到期為設計行為，不送。
- TestLink b15 回填（2026-11-11，使用者確認預覽後寫入）：正式輪 NODE1 2026-11-10_15-15-35、NODE3 2026-11-10_11-42-15
  （已記入 reports/_index/formal_runs.yaml）；254 筆 p 248／f 6，0 錯誤。6 個 f 以 testlink_link_bug 連結（各多一筆 f execution，
  TestLink 不回報連結成功與否）：6675／6676／6677／7109 與 7223 → #263239，7173 → #263277。
- 框架問題（未修）：`ensure_prerequisite_profile` 把 HTTP 500 當成不存在；`ensure_profile_exists_or_skip` 把 no privilege 當 Skip；
  ont_service_by_sn 缺 ONT 存在前置檢查。

### 2026-11-06 b15 NODE1／NODE3 回歸（Claude Code）

- 分支 claude/b15-regression（基準 c7d5673，未設 upstream）；configs/ems.yaml 兩個 target version 改為 b15，未提交。
  使用者確認 .8（ubuntu）已升 b15、NODE1／NODE3 由 .8 納管且無人使用，授權完整測試含破壞性測試。
- 三輪完整回歸（`run_multi_node.py --run-full-testcases`，reports/multi_node/）：
  R1 2026-11-06_09-59-10（NODE1 通過 191／失敗 4＋1 error；NODE3 通過 286／失敗 30，當時有其他 client 使用 .8）、
  R2 2026-11-06_14-36-05（NODE3 305／11；NODE1 191／7）、R3 2026-11-06_16-46-23（NODE1 201／1；NODE3 307／9）。
  2026-11-06_13-34-39 那輪因 .8 於 13:52 重啟而手動停止，不列入比對；停止後確認無測試殘留。
- 總結報表：reports/03.00.11 (AAVV.221) b15_ubuntu/b15_regression_summary_2026-11-06_NODE1_NODE3.html，
  證據（最小重現腳本與 JSONL、報表產生腳本）在同目錄 b15_evidence_2026-11-06/。
- 主要現象（Root Cause 皆未確認）：
  - 有效 readwrite session 零星收到 `You have no privilege to do this.`，三輪打在不同 case；
    不跑測試的最小重現（登入一次後連續 GET）692 筆中 7 筆，疑似 b15 API 問題。
  - NODE1 `test_post_ont_service_by_sn` 三輪都失敗（ONT service 停在 Wait），唯一穩定失敗，未調查。
  - NODE3 `This card is not NXC/NXP card`：R2 15:02–15:03 三次、單項重跑一次、R3 零次；卡片與 alarm 正常，需 .8 EMS server log。
  - R1 才有的 Invalid session id、ONT 查無資料、DELETE usersession 回 SQLNonTransientConnectionException、EMS1-7020，之後未再出現。
- 框架問題（未修）：services/profile/service.py `ensure_profile_exists_or_skip` 把 no privilege 當 Skip，會掩蓋同一問題。
- 後續（見上一條）：no privilege 已開為 #263277；ont_service_by_sn 已查明為環境問題。
  仍未完成：NODE3 上 34 組舊 `#RestApi_*_3011bXX_N3_*` SFU template 是否清理。

## 下一步

標記：〔離線〕可直接做；〔需決定〕等使用者決策；〔需實機〕需使用者授權並指定 node。

retro 計畫（2026-10-20 核准）的離線 PR A～I 已全部完成；剩下的是待實機與待決策項目：

- [RC-4]〔離線〕txt Summary 行加 Skip 數（b12 NODE1 的 `152 Pass / 0 Fail` 看不出 26 個 skipped）；corp 只把 Summary 當字串，
  但會寫進 TestLink notes，格式需使用者確認。
- [RC-5]〔需決定〕回填前把關已在 UseTestlink claude/report-readiness-gate 實作（見 2026-10-27 RC-5 條目），待合併與發版安裝。
- [RC-6]〔需決定〕b12 NODE1：formal_runs.yaml 標 2026-09-22 為正式執行，TestLink 仍是 09-08 的結果，需決定補回填或改正式執行。
- [RC-7]〔需實機〕redhat .100 在 10-22／10-27 多次出現 RemoteDisconnected／讀取逾時／拒絕連線，重跑皆通過；若持續發生再評估。
- [RC-2]〔需決定〕RAD 摘要（7056／7107／7108）沒開 --auth-matrix 時被 skip 仍不會出現在報表，是否改為列出 Skip。
- [RC-3]〔需實機〕PR #34 的 mutating 情境（6667～6669 主測試 skip）尚未實機驗證；10-22 完整測試中這三個都通過，
  沒有遇到 skip 的情況。

- [R-SLP]〔需實機〕（ACL 部分已完成）inventory／provision 輪詢前固定 30／15 秒以 initial_delay=0 實測，
  完成後刪除 tests/test_no_fixed_sleep.py 對應的 KNOWN_SLEEPS 條目。
- [R-REG]〔需實機〕（password／session id 已驗證）registid、CLI registration-id、teardown statusDetails
  待有寫入／teardown 失敗的回歸時以 `--redact-reports` 確認。

使用者決策（2026-10-20 已定：D6 skill 名稱 pr-description；D7 專案 settings.json／.gitattributes 這輪不做）：

- [D1]〔需決定〕（2026-10-20 使用者已定：本機報表保留原值）既有 reports/ 不需清理明文；此項可關閉。
- [D3]〔需決定〕（重複副本已清理）保留的 9 個 DIFFERENT／NO_ARCHIVE 目錄與 b1–b9 是否再以 tools/archive_reports.py 歸檔。
- [D4]〔需決定〕曾貼入對話或整檔讀出的測試帳密是否輪替。
- [D5]〔需決定〕Codex 之後是否仍在本 repo 使用（影響 skill 原檔位置）。

b15（2026-11-11）：

- [B15-7223]〔需實機〕EMS1-7223 restore 回 Success 但未套用：需使用者同意在 NODE3 重現，重現到才起草 bug。
- [B15-TL]〔離線〕到 TestLink 頁面確認 6 個 f case 的 bug 清單有顯示連結（API 不回報）。
- [B15-FW]〔離線〕框架：ensure_prerequisite_profile 500 當不存在、ensure_profile_exists_or_skip 吞 no privilege、
  ont_service_by_sn 加 ONT 存在前置檢查。
- [B15-ATT]〔需決定〕確認 #263239 附件 rd_repro_ont_unreg_500.py 已上傳。

既有事項：

- [B13]〔需決定〕b13_redhat：既有報表明文清理（同 D1）；RAD external 11:40～15:59 恢復原因；
  formal_runs.yaml 正式執行；TestLink build／回填；configs/ems.yaml b13 版本是否已提交需核對。
- [TD]〔需實機〕（PR-1／PR-2 已完成）累積幾次回歸的 `ONT baseline` 輪詢次數後，檢討 SLOW 門檻 12 次是否合適。
- [EMS100]〔需實機〕.100 連線中斷判定為 server 資源不足（ADR 0002）；下次完整測試確認
  `EMS Connection Errors` 行與重送恢復，仍頻繁再以報表時間點查 .100 log。
- [SOP]〔需決定〕docs/sop/ 的 SOP docx（9/22 版）未納入版控；要給同事用需先改寫為 Markdown 並更新
  EMS server 切換與 qa-integration-agent 回填流程（repo 為 Public）。docs/qa_bug_drafts/ 維持不進版控。
- [SFU]〔需實機〕ONT SFU 間歇 `Wait`／teardown HTTP 500：測試期間以 CLI 記錄 ONT 狀態，確認
  provision template 套用／還原是否觸發 ONT 重新註冊。
- [NNI]〔需決定〕NNI POST 移除 payload 未帶欄位、回 Fail 仍部分套用：待確認規格後決定是否用 /qa-bug-report。
- [FW]〔需實機〕NODE5／NODE7／NODE8 test_targets.local.yaml fw_version 仍帶後綴，需 CLI 確認後更新。
- [CI]〔離線〕推送到預設分支曾出現兩個 push run、其一被 concurrency 取消；原因未確認，持續發生再查。
- [DEP]〔離線〕依賴手動升級：改 requirements.txt 後確認 CI 與本機離線檢查通過。

## 後續更新方式

- 每個工作條目記錄：日期、負責工具、任務、分支／基準、修改範圍、驗證指令與結果、未執行原因、下一步。
- 只在任務完成或交接時更新一次，不逐步記帳。PR 編號、merge commit、CI run id 不寫入本檔，
  以 GitHub 與 git log 為準。
- 本檔只保留最近 1～2 筆工作條目，較舊的原文移到 docs/work-history/<YYYY-MM>.md，全檔維持在 120 行以內。
- 已解決的事項移除或精簡；尚未完成或缺證據的事項保留，並標上 ID 與類型。
