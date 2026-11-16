# 歷史逐筆發布時刻查核

查核日期 2026-11-16（台北）。範圍為凍結研究面板 718 個台灣交易日，六序列共 4,218 個非空選值位置。ALFRED 的按日版本核對已通過。正式逐筆發布時刻認證仍未通過。

| 序列 | 可查證的公開資料 | 尚缺證據 |
|---|---|---|
| DEXTAUS | 聯準會 H.10 歷史期次日期及每週發布時程。718 個決策日的日期和時程檢查已有紀錄。 | 對應版本的歷史實際發布時間戳。 |
| DGS10 | 聯準會 H.15 官方 RSS 回傳一筆觀測，觀測日為 2026-11-12，頻道時間為 2026-11-13T16:15:00-05:00。該觀測日晚於本次歷史面板。 | 面板期間各期次的留存 RSS 或同等發布紀錄。 |
| NFCI | 芝加哥聯準銀行公告美東週三 08:30 更新，部分假日週改至週四。 | 每一期實際發布時間，含歷史修訂。 |
| VIXCLS | Cboe 每日收盤已核對。Main Channel Tick Data 公開 ZIP 樣本含 59 筆 VIX 盤中紀錄，有時區偏移與毫秒級時間戳。樣本僅涵蓋 2024-09-03 02:15:01.261 至 02:29:31.321（檔內偏移 -05:00），沒有面板選用的當日收盤 20.72。 | 每一所需收盤值的 Cboe 發布紀錄，及任何相關修訂的時間。 |
| BAMLH0A0HYM2、BAMLC0A0CM | ALFRED 已核對面板所選版本。ICE 產品頁列有歷史資料與傳輸服務。 | 兩個指定 OAS 序列的首次發布與修訂時間戳。產品頁未確認具備這些欄位。 |

ALFRED 以日期記錄來源或供應商的發布日期，必要時採 FRED 首次可得日期。來源發布、資料轉載與觀測時間分別記錄才足以支持逐筆認證。收盤價、例行公布時程、RSS 觀測時間及最新序列更新時間各自有不同含義。

## 查驗來源

- [H.10 歷史期次](https://www.federalreserve.gov/releases/h10/releaseDates.json) · [既有 H.10 核對](pit_publication_evidence_scope.json)
- [H.15 十年期官方 RSS](https://www.federalreserve.gov/feeds/Data/H15_H15_RIFLGFCY10_N.B.XML) · SHA-256 `e3b8fb06be36dae73589d681745f7890b165334d1db0542ad317f7245966fa2e`
- [NFCI 公布時程](https://www.chicagofed.org/research/data/nfci/current-data)
- [Cboe Main Channel Tick Data](https://datashop.cboe.com/main-channel-tick-data) · [官方 ZIP 樣本](https://datashop.cboe.com/download/sample/257) · SHA-256 `5cad6536329cb7cff10c45977ca4540cf942858f83d04d62f0fee8bb037fbb22`
- [ICE 固定收益指數資料](https://developer.ice.com/fixed-income-data-services/catalog/ice-data-indices-fixed-income-indices)
- [ALFRED 發布日期說明](https://alfred.stlouisfed.org/help) · [版本核對](alfred_vintage_interval_verification.json)

正式發布時間關卡維持 BLOCKED。取得完整來源證據時，須能連結序列、觀測日期、數值或版本、含時區的實際發布時間及原始來源檔。
