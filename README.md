# 臺股開盤前風向提醒機器人

一個自動化爬蟲系統，每日彙整臺股大盤重要技術指標並透過 Telegram 推播，協助交易決策。

## 功能特色

- 📊 **自動化數據收集**：每日自動爬取多個數據源
- 🔄 **多指標彙整**：整合大盤指數、台指期夜盤、VIX、美股恐懼貪婪指數、台積電 ADR 比較、券資比、期貨未平倉、融資融券等指標
- 🤖 **AI 簡評**：呼叫 Claude API，針對當日數據自動生成一段約 50 字的三句式中文簡評
- 📱 **Telegram 推播**：分區視覺化格式，附燈號與變化幅度判讀，開盤前一次看完
- ⏰ **交易日檢查**：僅在交易日執行，避免無效運行
- 🐳 **Docker 支援**：容器化部署，內建 Playwright 瀏覽器
- ☁️ **雲端部署**：支援 Google Cloud Platform 自動化運行，並透過 GCS 同步歷史資料以計算逐日變化

## 監控指標

### 1. 券資比 (TWSE)

**說明**：衡量當日融券（做空）與融資（槓桿買進）行為相對強弱的指標。

**為何可觀察大盤**：券資比變動反映市場槓桿與多空偏好；短期內大幅上升可能代表做空力量累積或融資縮手（偏空訊號），但在過度做空情況下則可能觸發回補，成為反向警訊。

**資料來源**：使用臺灣證券交易所 API 回傳資料後計算得出結果。

### 2. 臺指選擇權波動率 (VIX)

**說明**：俗稱臺股的「恐懼指標」，由選擇權隱含波動率計算的指標，數值越高表示市場預期未來波動越大，也代表情緒緊張。

**為何可觀察大盤**：VIX 上升通常伴隨避險需求增加，抑制追價並可能導致短期回檔；VIX 下降則代表風險偏好回升，有利多方延續或反彈。

**資料來源**：採用網路爬蟲取得回傳內容。

### 3. 臺股期貨未平倉口數（外資 / 自營商 / 投信）

**說明**：顯示各類參與者持有的期貨淨部位量，正負或增減代表押注方向與規模變化。

**為何可觀察大盤**：外資、大型交易方部位變化往往與資金流向相關：外資做空可能對指數造成壓力；國內投信、自營若擴大多單，則提供短中期支撐。綜合三方動向可看出趨勢延續或轉折可能。

**資料來源**：採用網路爬蟲取得回傳內容。

### 4. 台指期夜盤指數

**說明**：台指期夜盤收盤指數、漲跌與漲跌幅，反映美股與國際盤夜間對台股的潛在影響。

**為何可觀察大盤**：夜盤走勢常被視為開盤前對隔夜風險的初步參考，可協助判斷開盤可能的跳空方向。

**資料來源**：透過 Playwright 取得 CMoney 台指期夜盤頁面的官方計算資料。

### 5. 大盤融資融券（餘額／增減／使用率／維持率）

**說明**：大盤融資餘額、融券餘額及其增減、使用率，以及融資維持率，衡量槓桿資金參與規模與抗跌能力。

**為何可觀察大盤**：高槓桿參與可放大行情，下跌時容易因強制平倉加速回檔；維持率下降至低檔易引發保證金追繳（俗稱斷頭），維持率穩健則有助於市場穩定。融資（金額）與融券（張數）單位不同，本專案分開呈現、不互相運算。

**資料來源**：透過 Playwright 攔截 CMoney 融資融券頁面的官方計算 API（`GetMarketMarginTradingInfo`），直接取得已計算好的數值，不再自行用個股融資張數×收盤價加總計算。

**注意事項**：v1.0 版本曾自行計算大盤融資維持率，與券商數值有 1%-2% 誤差；v2.0 改採 CMoney 官方計算數值後已不再需要自行估算，相關舊邏輯（`maintenance_calc.py`）仍保留在程式碼中但預設不執行。

### 6. 美股恐懼貪婪指數（CNN Fear & Greed Index）

**說明**：CNN 編製的美股市場情緒指數（0-100），綜合多項市場技術指標計算，反映美股投資人整體偏向恐懼或貪婪。

**為何可觀察大盤**：美股情緒常透過夜盤、ADR 等管道傳導至台股開盤，極端恐懼或貪婪時常伴隨較大波動。

**資料來源**：CNN 背後資料 API（`production.dataviz.cnn.io`），依分數分為極度恐懼、恐懼、中性、貪婪、極度貪婪五級。

### 7. 台積電 ADR 與台股 2330 隱含溢價/折價

**說明**：以台積電紐約 ADR（TSM，1 ADR：5 股）前一交易日收盤價，換算美元兌台幣匯率後，與台股 2330 前一交易日收盤價比較，得出隱含溢價或折價百分比。

**為何可觀察大盤**：ADR 反映美股交易時段（台股休市時）的台積電股價變動，常被視為台股開盤的領先指標之一，台積電在大盤權重高，對指數影響顯著。

**資料來源**：`yfinance`（`TSM`、`2330.TW`、`TWD=X`）。

### 8. AI 簡評（Claude API）

**說明**：彙整當日夜盤、VIX、美股恐懼貪婪指數、券資比、期貨未平倉、融資融券等關鍵數據，呼叫 Claude API（預設 `claude-haiku-4-5-20251001`）生成一段約 50 字的三句式中文簡評：第一句比較夜盤與前一日收盤、第二句點出最值得注意的異常指標、第三句總結整體偏多/偏空/觀望判斷。

**容錯設計**：未設定 `ANTHROPIC_API_KEY`、API 呼叫失敗或逾時時，直接跳過此區塊，不影響其他指標正常推播。

## 技術架構

### 資料來源

- **臺灣證券交易所 (TWSE) API、網路爬蟲**：券資比、加權股價指數
- **臺灣期貨交易所 (TAIFEX) 網路爬蟲**：VIX 指數、期貨未平倉口數
- **CMoney（透過 Playwright 攔截官方計算 API）**：大盤融資融券（餘額/增減/使用率/維持率）、台指期夜盤指數
- **CNN（背後資料 API）**：美股恐懼貪婪指數
- **yfinance**：台積電 ADR（TSM）、台股 2330、USD/TWD 匯率
- **Claude API（Anthropic）**：AI 簡評文字生成

### 技術棧

- **Python 3.10+**
- **主要套件**：
  - `requests` - HTTP 請求
  - `pandas` - 數據處理
  - `playwright` - 瀏覽器自動化（CMoney 爬蟲、VIX 備用方案）
  - `lxml` - HTML 解析
  - `pandas_market_calendars` - 交易日判斷
  - `google-cloud-storage` - 雲端歷史存檔同步（用於計算逐日變化）

### 部署方式

- **本地執行**：可直接在本地環境運行
- **Docker 容器**：支援容器化部署，預設安裝 Playwright 瀏覽器
- **Google Cloud Platform**：支援雲端自動化運行（建議運行時間：每日 08:00，開盤前），並透過 GCS bucket 同步每日存檔，讓 Cloud Run Job 在無持久化磁碟的情況下仍能計算與前一交易日的變化
- **機密資訊管理**：`TG_BOT_TOKEN`、`TG_CHAT_ID`、`ANTHROPIC_API_KEY` 等機密值皆透過 GCP Secret Manager 儲存，Cloud Run Job 以 `secretKeyRef` 方式讀取並限制只有 `tw-stock-runner` 服務帳戶可存取，不會寫入程式碼、Docker image 或環境變數明文中

## 為什麼選擇這些指標？

這些指標是近幾年操作臺股開盤前，都會參考的指標，主要是透過這些指標能理解今日臺股的大致走勢，避免追高殺低。但這些指標分散在不同網站，故透過程式碼將其蒐集後一次推播，降低監控負擔並協助交易決策。

## 運行時間的選擇

相關資料皆為前一交易日收盤後才會更新的資料，因此設每日更新一次。v2.0 將推播時間由 00:02 調整為開盤前的 08:00，定位更貼近「開盤前提醒」。如當天非開盤日，系統會自動跳過執行。

## 安裝與設定

### 1. 環境需求

- Python 3.10 或以上
- pip

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 3. 環境變數設定

建立 `.env` 檔案（或設定系統環境變數）：

```bash
# Telegram Bot 設定（必填）
TG_BOT_TOKEN=your_telegram_bot_token
TG_CHAT_ID=your_telegram_chat_id

# 執行設定（選填）
AUTO_SEND=true          # 是否自動發送訊息
DRY_RUN=false           # 是否為測試模式
ORDERED_SCRAPERS=twse_margin_api,twse_mi_index,cmoney_futures_night,VIXTWN,taifex_futures,cmoney_margin,cnn_fear_greed,tsm_adr_compare
PARALLEL=false          # 是否並行執行
MAX_WORKERS=4           # 並行執行時的最大工作數
RETRY=1                 # 失敗重試次數
LOG_LEVEL=INFO          # 日誌級別
SKIP_TRADING_DAY_CHECK=false  # 是否跳過交易日檢查
RESULTS_GCS_BUCKET=     # （雲端部署用）GCS bucket 名稱，用於同步歷史存檔以計算逐日變化，本地執行可留空

# AI 簡評（選填）
ANTHROPIC_API_KEY=      # 設定後才會產生 AI 簡評區塊，未設定則自動跳過
AI_SUMMARY_ENABLED=true # 設為 false 可關閉 AI 簡評
AI_SUMMARY_MODEL=claude-haiku-4-5-20251001
```

### VIX 兩段式排程（避免資料尚未更新導致顯示異常值）

VIX 來源 API 偶爾會在資料尚未更新時回傳無效的 `0`，程式已會自動判定 `<=0` 為錯誤、不覆蓋快取，並在當次抓取失敗時 fallback 使用 `results/latest_taifex_vix.json` 的前次有效值（顯示時會加註「（快取）」）。若要讓快取更新鮮，可額外在 00:00 左右新增一個只跑 VIX、不推播的排程：

```bash
ORDERED_SCRAPERS=VIXTWN AUTO_SEND=false python main.py
```

雲端部署時，可在既有 Cloud Run Job 之外，另建一個 Cloud Scheduler 於 00:00（Asia/Taipei）觸發同一個 Job，並覆寫 `ORDERED_SCRAPERS=VIXTWN`、`AUTO_SEND=false`；08:00 的既有排程維持原樣即可。

### 4. 執行

```bash
python main.py
```

## 專案結構

```
TW_stock_detect/
├── main.py                 # 主程式入口
├── scrapers/               # 爬蟲模組
│   ├── twse_margin_api.py        # 券資比爬蟲
│   ├── twse_mi_index.py          # 加權股價指數爬蟲
│   ├── cmoney_futures_night.py   # 台指期夜盤爬蟲（Playwright）
│   ├── VIXTWN.py                 # VIX 指數爬蟲
│   ├── taifex_futures.py         # 期貨未平倉口數爬蟲
│   ├── cmoney_margin.py          # 大盤融資融券爬蟲（Playwright）
│   ├── cnn_fear_greed.py         # 美股恐懼貪婪指數爬蟲
│   ├── tsm_adr_compare.py        # 台積電 ADR 與台股 2330 比較
│   ├── ai_summary.py             # AI 簡評（Claude API）
│   ├── maintenance_calc.py       # 舊版融資維持率自行計算（保留、預設不執行）
│   ├── gcs_sync.py               # 雲端歷史存檔同步（GCS）
│   ├── compose_notification.py   # 訊息組裝
│   ├── tg_send.py                # Telegram 發送
│   ├── trading_day.py            # 交易日判斷
│   └── utils.py                  # 工具函數
├── results/                # 數據輸出目錄（不包含在版本控制）
├── requirements.txt        # Python 依賴
├── Dockerfile              # Docker 映像檔設定
├── Changelog.txt           # 版本更新日誌
└── README.md               # 本檔案
```

## Docker 部署

### 建立映像檔

```bash
docker build -t tw-stock-detect .
# 預設已內建安裝 Playwright 瀏覽器（INSTALL_PLAYWRIGHT 預設為 true）
```

### 執行容器

```bash
docker run --env-file .env tw-stock-detect
```

## 執行流程

1. **交易日檢查**：確認當日為臺股交易日
2. **歷史存檔同步**：若設定 `RESULTS_GCS_BUCKET`，從 GCS 下載前一交易日的存檔（供計算逐日變化）
3. **數據爬取**：依序執行各爬蟲模組
4. **數據彙整**：將各模組結果整合為摘要
5. **訊息組裝**：將摘要轉換為分區視覺化的中文通知訊息
6. **Telegram 推播**：發送訊息至指定聊天室
7. **歷史存檔回傳**：若設定 `RESULTS_GCS_BUCKET`，將當日存檔上傳回 GCS，供下次執行比較使用

## 注意事項

- 本專案僅供學習與研究使用
- 數據來源為公開資訊，不保證即時性與準確性
- 投資決策請自行判斷，本工具不構成投資建議
- 請遵守各數據來源網站的使用條款與爬蟲規範
- 大盤融資融券數值（v2.0 起）改採 CMoney 官方計算結果，不再自行加總計算

## 授權

本專案為個人專案，僅供參考學習。

## 聯絡資訊

如有問題或建議，歡迎提出 Issue 或 Pull Request。

