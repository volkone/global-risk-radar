# P2-03 網站整合｜最終驗收與版本凍結

驗收登錄日期：2026-11-15（Asia/Taipei）

## 驗收結論

**PASS — 研究版網站整合功能**。此結論僅限於已執行的自動化測試涵蓋範圍，**不代表模型具備正式預測效力或交易授權**。

- 驗收程式碼 SHA：`9648547b39819a82fa754cc4cc25041563c34089`
- 凍結參照分支：`freeze/p2-03-accepted-2026-11-15`，指向上述 SHA。
- Chromium 瀏覽器驗收：GitHub Actions [#43600176686](https://github.com/volkone/global-risk-radar/actions/runs/43600176686)，`completed / success`，2026-11-14 13:31:49 UTC。
- 資料契約與 JavaScript 語法回歸：GitHub Actions [#43599819007](https://github.com/volkone/global-risk-radar/actions/runs/43599819007)，`completed / success`。
- 同一測試版本的網站部署：GitHub Actions [#43600176679](https://github.com/volkone/global-risk-radar/actions/runs/43600176679)，`completed / success`。

## 驗收覆蓋範圍

1. Chromium 以本地 HTTP server 開啟 `docs/index.html`，等待 `#p203-research[data-status="loaded"]`。
2. 比對三段 Walk-Forward 5d/20d 命中率及合併值，與 `docs/p2_02_extended_validation.json` 一致。
3. 比對六因子 5d/20d 成對消融差異，與 `docs/p2_02_failure_and_multiplicity.json` 一致。
4. 比對上漲市場轉弱研究之 5d/20d precision、base rate、Bonferroni p，與 `docs/p2_03_uptrend_early_warning_research.json` 一致。
5. 驗證研究區塊明示 `BLOCKED`、研究用途、不可作為交易訊號。
6. 驗證既有儀表板風險圖、因子明細、市場卡片仍能顯示；切換歷史序列與範圍不改動研究區塊。
7. 驗證無未處理的 JavaScript page errors 或 failed requests；測試上傳全頁截圖 artifact。

測試程式：`scripts/test_p203_browser.cjs`、`scripts/test_p203_dashboard_integration.py`。
工作流程：`.github/workflows/test_p203_browser.yml`、`.github/workflows/test_p203_dashboard.yml`。

## 版本凍結規則

凍結分支是**固定驗收版本參照**，不應用來開發或接收自動資料更新。後續開發只在 `main` 或新工作分支進行；任何更動 `docs/index.html`、`docs/dashboard.js`、`docs/p203_research.js` 或測試程式的提交，均應重新執行兩項驗收。Git 分支並非不可變物件；禁止移動此參照屬於專案治理約定，未宣稱已設定 GitHub branch protection。

## 未驗證與不授權事項

- 本次 Chromium 測試在 GitHub Actions runner 上使用本地 HTTP server，**不是公開 GitHub Pages 正式網址的端到端網路測試**；部署 workflow 成功亦不代表各地瀏覽器實際可用。
- 研究模型的統計顯著性、真正獨立的前瞻驗證、資料發布時間/PIT、期交所官方來源證據仍未達正式門檻。
- `docs/model_readiness.json` 仍為 `BLOCKED`；正式交易門檻、投資加碼指令、自動交易及正式預警一律不授權。
- 本文件只記錄已驗證的版本與結果，不將之視為 P2-04 完成證據。

## 下一步

進入 **P2-04 資料品質與官方來源認證**，優先補歷史發布時間、FRED vintage 與期交所獨立官方證據；保留前瞻蒐集與既有儀表板更新。
