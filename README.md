# 全球金融風險雷達
GitHub Pages + GitHub Actions，監測18項指標的資料可得性；首版已串接 FRED 與部分 Yahoo Finance 非官方行情。
網站預期網址：https://volkone.github.io/global-risk-radar/
每小時排程可能延遲，並非即時行情；Actions 在未活動的公開儲存庫可能停止排程。
在 Settings → Pages → Build and deployment → Source 選擇 GitHub Actions。
Telegram 通知：於 Settings → Secrets and variables → Actions 建立 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID。未設定時警報保留於 data.json，日後可重試。
注意：docs/data.json 公開可見，請勿放入任何個人資產或密鑰。
完整18項尚未全部串接；未取得的資料會明確顯示 unavailable。

## 台股急跌警戒

- 盤前以台北 07:30–09:00 的實際擷取為準。取前一個台股交易日收盤、近 20 個交易日的收盤高點，以及美東最近已收市交易日的費半與台積電 ADR。台股前一日跌達 3% 或 20 日回撤達 8%，同時兩個美股因子各跌達 2% 時，顯示研究警戒。來源缺值與盤前未執行會顯示各自狀態。
- 盤中由既有 GitHub Actions 每小時工作流程取快照。證交所 MIS 提供加權、櫃買、開盤缺口及報價，證交所與櫃買中心的公司名冊提供四碼股票母體。取當日一般交易的最後成交與參考價比較，跌停使用報價的下限。可比覆蓋低於 85% 時暫缺比例，報價逾 30 分鐘時標示為上次快照。盤後換成證交所與櫃買中心正式統計，分母為可比股票。
- 盤後以證交所各交易日上市融資餘額計算 1 日及 5 日變動，並列出現貨外資、投信、自營商及合計。自營商含自行買賣與避險。資料日與市場須一致。融資變動包含各種減碼與調整。
- 盤前新規則以網站研究提示呈現。台股主要收盤值、日期與回撤使用證交所 FMTQIK，回撤須有完整一年交易日的收盤。盤前 20 日使用同一官方序列。
- 排定交易日沿用專案官方日曆，並補入 [證交所開休市日期](https://www.twse.com.tw/zh/trading/holiday.html)及 [2026 年行憲紀念日](https://www.ntuh.gov.tw/ckfinder_file/ntuh/files/%E6%9C%80%E6%96%B0%E6%B6%88%E6%81%AF/2025/115%20%E5%B9%B4%E5%BA%A6%E5%9C%8B%E5%AE%9A%E5%81%87%E6%97%A5%E6%9A%A8%E9%81%B8%E8%88%89%E6%8A%95%E7%A5%A8%E6%97%A5.pdf)。台股日曆目前涵蓋到 2027 年底，臨時休市須更新日曆或等待官方資料。美東完成時間保守採 16:15，依 [NYSE 公布的交易日](https://www.nyse.com/trade/hours-calendars)檢查。
- 以 `python scripts/crash_watch_validation.py` 重跑 2000–2025 年的歷史驗證。輸入可指定已保存的來源 JSON。報告列出來源雜湊、兩個分段、命中及月均誤報。歷史美股可用時間採美東 16:15 的收盤代理，歷史檔涵蓋的共同交易日作為休市判斷。11/20 案例使用當時可知收盤資料重播，正式發報紀錄由日後盤前擷取累積。
