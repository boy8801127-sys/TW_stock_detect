# 臺股開盤前風向提醒機器人

一個自動化爬蟲系統，於開盤日00:30彙整臺股大盤重要技術指標並透過 Telegram 推播，協助交易決策。

## 功能特色

- 📊 **自動化數據收集**：每日自動爬取多個數據源
- 🔄 **多指標彙整**：整合五大關鍵技術指標
- 📱 **Telegram 推播**：自動發送每日市場分析報告
- ⏰ **交易日檢查**：僅在交易日執行，避免無效運行
- 🐳 **Docker 支援**：容器化部署，易於擴展

## 監控指標

1. **券資比 (TWSE)**
   - 衡量融券與融資行為相對強弱的指標
   - 反映市場槓桿與多空偏好

2. **臺指選擇權波動率 (VIX)**
   - 俗稱臺股的「恐懼指標」
   - 數值越高表示市場預期未來波動越大

3. **臺股期貨未平倉口數**
   - 外資、自營商、投信三大參與者的期貨淨部位
   - 反映資金流向與趨勢變化

4. **所有融資上市股票市值**
   - 市場中以融資方式持有的股票總市值
   - 代表槓桿資金的參與規模

5. **大盤融資維持率**
   - 衡量整體融資戶維持保證金比例的指標
   - 數值下降可能引發強制平倉風險

## 技術架構

### 資料來源

- **臺灣證券交易所 (TWSE) API**：券資比、加權股價指數、融資融券數據
- **臺灣期貨交易所 (TAIFEX)**：VIX 指數、期貨未平倉口數
- **網路爬蟲**：補充數據來源

### 技術棧

- **Python 3.10+**
- **主要套件**：
  - `requests` - HTTP 請求
  - `pandas` - 數據處理
  - `playwright` - 瀏覽器自動化（備用方案）
  - `lxml` - HTML 解析
  - `pandas_market_calendars` - 交易日判斷

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
ORDERED_SCRAPERS=twse_margin_api,twse_mi_index,VIXTWN,taifex_futures,maintenance_calc
PARALLEL=false          # 是否並行執行
MAX_WORKERS=4           # 並行執行時的最大工作數
RETRY=1                 # 失敗重試次數
LOG_LEVEL=INFO          # 日誌級別
SKIP_TRADING_DAY_CHECK=false  # 是否跳過交易日檢查
```

### 4. 執行

```bash
python main.py
```

## 專案結構

```
TW_stock_detect/
├── main.py                 # 主程式入口
├── scrapers/               # 爬蟲模組
│   ├── twse_margin_api.py  # 券資比爬蟲
│   ├── twse_mi_index.py    # 加權股價指數爬蟲
│   ├── VIXTWN.py           # VIX 指數爬蟲
│   ├── taifex_futures.py   # 期貨未平倉口數爬蟲
│   ├── maintenance_calc.py # 融資維持率計算
│   ├── compose_notification.py  # 訊息組裝
│   ├── tg_send.py          # Telegram 發送
│   ├── trading_day.py      # 交易日判斷
│   └── utils.py             # 工具函數
├── results/                # 數據輸出目錄（不包含在版本控制）
├── requirements.txt        # Python 依賴
├── Dockerfile              # Docker 映像檔設定
└── README.md               # 本檔案
```

## Docker 部署

### 建立映像檔

```bash
docker build -t tw-stock-detect .
```

### 執行容器

```bash
docker run --env-file .env tw-stock-detect
```

## 執行流程

1. **交易日檢查**：確認當日為臺股交易日
2. **數據爬取**：依序執行各爬蟲模組
3. **數據彙整**：將各模組結果整合為摘要
4. **訊息組裝**：將摘要轉換為中文通知訊息
5. **Telegram 推播**：發送訊息至指定聊天室

## 注意事項

- 本專案僅供學習與研究使用
- 數據來源為公開資訊，不保證即時性與準確性
- 投資決策請自行判斷，本工具不構成投資建議
- 請遵守各數據來源網站的使用條款與爬蟲規範

## 授權

本專案為個人專案，僅供參考學習。

## 聯絡資訊

如有問題或建議，歡迎提出 Issue 或 Pull Request。

