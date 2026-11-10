# 全球金融風險雷達
GitHub Pages + GitHub Actions，監測18項指標的資料可得性；首版已串接 FRED 與部分 Yahoo Finance 非官方行情。
網站預期網址：https://volkone.github.io/global-risk-radar/
每小時排程可能延遲，並非即時行情；Actions 在未活動的公開儲存庫可能停止排程。
在 Settings → Pages → Build and deployment → Source 選擇 GitHub Actions。
Telegram 通知：於 Settings → Secrets and variables → Actions 建立 TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID。未設定時警報保留於 data.json，日後可重試。
注意：docs/data.json 公開可見，請勿放入任何個人資產或密鑰。
完整18項尚未全部串接；未取得的資料會明確顯示 unavailable。
