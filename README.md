# Scrapling API

使用 FastAPI 與 Scrapling 建立的網頁抓取 API，可將目標網頁的 HTML 轉換為 Markdown。

此服務支援靜態抓取、JavaScript 動態頁面抓取，以及自動判斷模式，適合提供給 n8n、內部工具或其他程式呼叫。

https://scrapling.readthedocs.io/en/latest/index.html

https://github.com/D4Vinci/Scrapling

## 功能特色

- 支援靜態頁面與 JavaScript 動態頁面
- `auto` 模式會先嘗試靜態抓取，必要時自動切換為動態抓取
- **自動展開**：具備自動點擊網頁常見「閱讀更多」或摺疊內容的能力
- **點擊模擬**：支援在抓取前執行手動指定的 CSS Selector 點擊操作
- 支援 JSON 或純 Markdown 回應格式
- 使用 `x-api-key` Header 進行簡單 API 驗證
- 可透過 `.env` 調整逾時、重試、等待時間與自動判斷條件
- 提供 Docker Compose 部署方式

## 目錄

- [運作流程](#運作流程)
- [專案檔案](#專案檔案)
- [快速開始](#快速開始)
- [環境變數設定](#環境變數設定)
- [API 使用方式](#api-使用方式)
- [抓取模式](#抓取模式)
- [自動內容展開與點擊模擬](#自動內容展開與點擊模擬)
- [Auto 模式判斷方式](#auto-模式判斷方式)
- [容器維護](#容器維護)
- [常見問題](#常見問題)

## 運作流程

```text
Client 
    |
    | POST /scrape
    | x-api-key: YOUR_API_KEY
    v
FastAPI
    |
    +-- mode=static  ----> AsyncFetcher
    |
    +-- mode=dynamic ----> DynamicFetcher (含點擊/展開互動)
    |
    +-- mode=auto
          |
          +-- 先使用 AsyncFetcher
          |
          +-- 判斷為 JavaScript 空殼頁、內容過短或帶有點擊需求
                  |
                  +-- 改用 DynamicFetcher
    |
    v
HTML -> Markdown -> JSON 或 Markdown 回應
```

## 專案檔案

```text
scrapling-api/
├── Dockerfile
├── docker-compose.yml
├── main.py
└── .env
```

### `Dockerfile`

以 `pyd4vinci/scrapling` 為基底映像，安裝 Scrapling、FastAPI、Uvicorn 與 Markdownify，並啟動 API 服務。

```dockerfile
FROM pyd4vinci/scrapling

WORKDIR /service

RUN python -m pip install --no-cache-dir "scrapling[all]" fastapi "uvicorn[standard]\" markdownify

COPY main.py .

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### `docker-compose.yml`

負責建立容器、載入 `.env`、設定自動重啟，並將主機的 `8080` Port 對應到容器的 `8080` Port。

```yaml
services:
  scrapling-api:
    build: .
    container_name: scrapling-api
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "8080:8080"
```

### `main.py`

FastAPI 主程式，提供以下端點：

- `GET /health`：健康檢查
- `POST /scrape`：抓取網頁並轉換為 Markdown
- `GET /docs`：FastAPI 自動產生的互動式 API 文件

### `.env`

保存 API Key 與抓取行為設定。`main.py` 使用 `os.getenv()` 讀取環境變數，Docker Compose 會透過 `env_file` 將 `.env` 注入容器。

## 快速開始

### 1. 準備檔案

將 `Dockerfile`、`docker-compose.yml`、`main.py` 與 `.env` 放在同一個資料夾。

```bash
cd ~/scrapling-api
```

### 2. 修改 `.env`

部署前至少要更換 API Key，並建議將動態抓取逾時設定為 60 秒。

```env
API_KEY=replace-with-a-long-random-secret
DYNAMIC_TIMEOUT=60000
```

> 不要使用 `123456` 等容易猜測的密鑰，也不要將正式 `.env` 上傳到 GitHub。

### 3. 建立並啟動容器

```bash
docker compose up -d --build
```

### 4. 確認容器狀態

```bash
docker compose ps
docker logs --tail=100 scrapling-api
```

### 5. 執行健康檢查

```bash
curl http://localhost:8080/health
```

正常回應：

```json
{"ok":true}
```

### 6. 開啟 API 文件

瀏覽器開啟：

```text
http://localhost:8080/docs
```

## 環境變數設定

| 參數 | 預設值 | 單位 | 說明 |
| --- | ---: | --- | --- |
| `API_KEY` | 無 | - | API 驗證密鑰，呼叫時必須放在 `x-api-key` Header |
| `STATIC_TIMEOUT` | `20` | 秒 | 靜態抓取等待回應的最長時間 |
| `STATIC_RETRIES` | `2` | 次 | 靜態抓取失敗時的重試次數 |
| `STATIC_STEALTHY_HEADERS` | `true` | 布林值 | 靜態抓取是否加入類似瀏覽器的 HTTP Headers |
| `DYNAMIC_TIMEOUT` | `60000` | 毫秒 | 動態瀏覽器抓取的最長載入時間 |
| `DYNAMIC_WAIT` | `5000` | 毫秒 | 頁面載入後，額外等待多久才讀取 HTML |
| `DYNAMIC_NETWORK_IDLE` | `true` | 布林值 | 是否等待網路活動進入閒置狀態 |
| `DYNAMIC_DISABLE_RESOURCES` | `false` | 布林值 | 是否阻擋 CSS、圖片、字型等資源 |
| `AUTO_MIN_HTML_LENGTH` | `1000` | 字元 | 靜態 HTML 少於此長度時，`auto` 模式改用動態抓取 |
| `EXTRA_JS_SIGNALS` | 空白 | - | 額外的 JavaScript 頁面辨識關鍵字，以 `\|` 分隔 |
| `AUTO_EXPAND_DEFAULT` | `true` | 布林值 | 是否預設啟動自動內容展開功能 |
| `AUTO_EXPAND_KEYWORDS` | (內建列表) | - | 觸發點擊的關鍵字列表，以 `\|` 分隔 |
| `AUTO_EXPAND_WAIT_TIMEOUT` | `15000` | 毫秒 | 等待展開按鍵出現的最長時間 |
| `AUTO_EXPAND_AFTER_CLICK_WAIT` | `1000` | 毫秒 | 點擊按鈕後，額外等待資料載入的時間 |
| `MAX_CLICK_SELECTORS` | `20` | 次 | 單次請求允許手動提供的 CSS Selector 數量上限 |
| `MAX_CLICKS_PER_SELECTOR` | `20` | 次 | 每個 Selector 最多連續點擊次數 |

## API 使用方式

### `GET /health`

確認服務是否正常運作。

```bash
curl http://localhost:8080/health
```

### `POST /scrape`

抓取指定網址，並將 HTML 轉換為 Markdown。

請求 Header：

```text
Content-Type: application/json
x-api-key: YOUR_API_KEY
```

JSON Body：

| 欄位 | 必填 | 預設值 | 可用值 | 說明 |
| --- | --- | --- | --- | --- |
| `url` | 是 | 無 | HTTP 或 HTTPS URL | 要抓取的目標網址 |
| `mode` | 否 | `auto` | `auto`, `static`, `dynamic` | 抓取模式 |
| `response_format` | 否 | `json` | `json`, `markdown` | 回應格式 |
| `auto_expand` | 否 | `true` | 布林值 | 針對此請求是否執行自動展開 (僅動態模式有效) |
| `click_selectors` | 否 | `[]` | List[str] | 手動指定要點擊的 CSS Selectors |

### 綜合使用範例 (含點擊模擬)

針對需要展開才能看到內容的頁面：

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{
    "url": "https://example.com/job-info",
    "mode": "auto",
    "auto_expand": true,
    "click_selectors": [".more-info-btn", "#details-tab"],
    "response_format": "markdown"
  }'
```

## 抓取模式

### `auto`

一般使用建議選擇此模式。

1. 先使用 `AsyncFetcher` 進行靜態抓取。
2. 檢查 HTML 是否包含 JavaScript 提示關鍵字或長度是否過短。
3. **若請求內帶有 `click_selectors`**，或者命中上述條件，系統會自動切換為 `DynamicFetcher` 進行瀏覽器模擬。

### `static`

只使用 `AsyncFetcher`。

優點：速度極快、資源消耗最低。
限制：無法取得 JavaScript 渲染後的內容，且**不支援點擊模擬功能**。

### `dynamic`

直接使用 `DynamicFetcher` 啟動瀏覽器抓取。

優點：適合 104、myF5、以及任何需要執行 JS 點擊或等待資源載入的網站。
限制：速度較慢、資源消耗較高。

## 自動內容展開與點擊模擬

本服務專門為「抓取完整文章」設計了互動機制：

- **自動展開**：會尋找頁面中符合關鍵字（如 `show more`, `read more`, `applies to`）且具備屬性 `aria-expanded="false"` 的按鈕自動點擊。
- **手動點擊**：透過 `click_selectors` 參數，你可以精準控制瀏覽器點擊特定的 UI 元素（例如多個分頁標籤、載入更多按鈕等）。
- **流程保護**：系統會透過 `MAX_CLICKS_PER_SELECTOR` 與超時機制保護，防止網頁因異常 Selector 導致無限點擊或佔用過多資源。

## Auto 模式判斷方式

靜態 HTML 出現以下內建文字時，`auto` 模式會改用動態抓取：

```text
doesn't work properly without javascript
enable javascript
please enable javascript
id="app"
id='app'
vue-start
css error
sorry to interrupt
```

遇到新的網站提示文字時，可在 `.env` 加入額外關鍵字設定 `EXTRA_JS_SIGNALS`。

## 容器維護

### 修改 `.env` 後套用設定

只修改 `.env` 時，不需要重新建立 image，但必須重新建立容器：

```bash
docker compose up -d --force-recreate
```

### 修改 `main.py` 或 `Dockerfile` 後重新建立

```bash
docker compose up -d --build
```

## 常見問題

### `401 Invalid API key`
原因：請求 Header 的 `x-api-key` 與伺服器設定不一致。

### `auto` 模式回傳 `CSS Error`、`Loading` 或不完整
處理方式：提高 `AUTO_MIN_HTML_LENGTH` 或將該頁面特有文字加入 `EXTRA_JS_SIGNALS`，也可以直接強制使用 `"mode":"dynamic"` 並視情況設定 `auto_expand: true`。
