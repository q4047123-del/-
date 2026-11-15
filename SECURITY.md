# 資安政策與漏洞回報 (Security Policy)

## 支援版本 (Supported Versions)

本專案目前針對以下版本提供安全性維護、Bug 修復與量化微結構更新：

| 版本 (Version) | 支援狀態 (Supported) | 備註說明 (Notes) |
| :--- | :---: | :--- |
| **V25.x** | :white_check_mark: | **最新主力版本**（全台股四板塊制霸＋Fugle 即時五檔＋手機響應式版） |
| **V24.x** | :white_check_mark: | 跨期歷史記憶與大師專屬選股/停利重構版（僅維護重大安全修復） |
| **V23.x** | :x: | 舊版架構（建議升級至 V25.0） |
| **< V23.0** | :x: | 已停止維護 (End of Life) |

---

## 🔑 API 金鑰與憑證安全準則 (API Key & Secret Management)

本專案支援串接 **Fugle 富果股市即時行情 API**。為確保您的帳戶與憑證安全，請嚴格遵守以下規範：

1. **禁止將私人 API Key 硬編碼上傳至公開倉庫**：
   * 在提交程式碼（Commit / Push）至公開的 GitHub Repository 前，請務必確認 `index.html` 與 Python 爬蟲腳本中**未包含**您個人的正式環境 API Key 或交易憑證。
   * 執行 Python 自動化更新腳本時，強烈建議使用環境變數（例如 `export FUGLE_API_KEY="您的金鑰"`）或 GitHub Actions Secrets 注入金鑰。
2. **純前端本地運行機制**：
   * 本模擬器採用純前端瀏覽器本地運算（Client-Side Execution）與 `localStorage` 快取，您在網頁輸入框填入的 Fugle API Key 僅用於您的瀏覽器直接與 `wss://api.fugle.tw` 建立加密連線，不會傳送至任何第三方伺服器。

---

## 🚨 回報資安漏洞 (Reporting a Vulnerability)

如果您在本專案的程式碼、跨站腳本防護（XSS，如外部 JSON / Excel 檔案匯入解析）或 API 串接邏輯中發現任何潛在的資安漏洞：

1. **請勿直接公開發佈於公開的 GitHub Issue**，以免漏洞在修補前遭到惡意利用。
2. **回報管道**：
   * 請透過本倉庫的 **GitHub Security Advisories**（點選上方 `Security` 頁籤 ➔ `Report a vulnerability`）提交私密回報。
   * 或直接發送私人訊息聯繫專案維護者，並附上漏洞重現步驟（Proof of Concept）。
3. **處理時程承諾**：
   * **確認收件**：我們會在收到回報後的 **48 小時內** 回覆確認。
   * **評估與修復**：若確認為有效漏洞，我們將於 **7 個工作天內** 發布修補更新（Patch），並在更新日誌中向您致謝。

---

## ⚠️ 免責聲明 (Disclaimer)

本專案為量化金融演算法、Barra 風險因子模型、Kalman 濾波狀態空間與台美股微結構之**教育與回測模擬器**，所有模擬交易、大師獨白與統計檢定數據均不構成任何真實世界之投資建議。
