# Scrapling API

使用 FastAPI 與 Scrapling 建立的網頁抓取 API，可將目標網頁的 HTML 轉換為 Markdown。

此服務支援靜態抓取、JavaScript 動態頁面抓取，以及自動判斷模式，適合提供給 n8n、內部工具或其他程式呼叫。

引用專案為:
https://github.com/D4Vinci/Scrapling
專案doc
https://scrapling.readthedocs.io/en/latest/index.html

## 功能特色

- 支援靜態頁面與 JavaScript 動態頁面
- `auto` 模式會先嘗試靜態抓取，必要時自動切換為動態抓取
- **自動展開**：具備自動點擊網頁常見「閱讀更多」或摺疊內容的能力
- **表單互動**：支援在 dynamic 模式先填入 input / textarea，再點擊按鈕並等待結果
- **點擊模擬**：支援在抓取前執行手動指定的 CSS Selector 點擊操作
- **內容清理與降噪**：Markdownify 前先移除 Nav、Footer、Aside、廣告、Cookie 橫幅等噪音節點
- **主體萃取**：可自動挑選 `article` / `main` / `[role=main]` 等主體內容，也可手動指定 `content_selector`
- **併發保護**：使用 Semaphore 限制同時執行的 DynamicFetcher 數量，避免瀏覽器併發拖垮 Docker 主機
- **User-Agent 輪換**：每次 `/scrape` 請求自動挑選 User-Agent，且 `auto` fallback 會沿用同一個 UA
- **Basic stealth**：在 dynamic 模式加入語系、時區、viewport、Chromium flag 與 `navigator.webdriver` 隱藏
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
- [內容清理與主體萃取](#內容清理與主體萃取)
- [Dynamic 併發與排隊控制](#dynamic-併發與排隊控制)
- [User-Agent 輪換與 Basic Stealth](#user-agent-輪換與-basic-stealth)
- [Dynamic 表單互動、內容展開與點擊模擬](#dynamic-表單互動內容展開與點擊模擬)
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
    +-- 每次請求挑選 User-Agent
    |
    +-- mode=static  ----> AsyncFetcher
    |
    +-- mode=dynamic ----> DynamicFetcher (含填表單/點擊/展開互動)
    |                         |
    |                         +-- Semaphore 控制瀏覽器併發
    |
    +-- mode=auto
          |
          +-- 先使用 AsyncFetcher
          |
          +-- 判斷為 JavaScript 空殼頁、內容過短或帶有表單/點擊需求
                  |
                  +-- 改用 DynamicFetcher
    |
    v
HTML -> Clean HTML -> Markdown -> Distilled Markdown -> JSON 或 Markdown 回應
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

以 `pyd4vinci/scrapling` 為基底映像，安裝 Scrapling、FastAPI、Uvicorn、Markdownify 與 BeautifulSoup，並啟動 API 服務。

```dockerfile
FROM pyd4vinci/scrapling

WORKDIR /service

RUN python -m pip install --no-cache-dir "scrapling[all]" fastapi "uvicorn[standard]" markdownify beautifulsoup4

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
| `DYNAMIC_CONCURRENCY` | `2` | 個 | 同時允許執行的 DynamicFetcher 數量 |
| `DYNAMIC_QUEUE_TIMEOUT` | `120` | 秒 | dynamic 請求等待併發名額的最長時間，超過回傳 503 |
| `DYNAMIC_STEALTH_BASIC` | `true` | 布林值 | 是否啟用 DynamicFetcher basic stealth 強化 |
| `DYNAMIC_LOCALE` | `zh-TW` | - | dynamic browser context 的 locale |
| `DYNAMIC_TIMEZONE` | `Asia/Taipei` | - | dynamic browser context 的 timezone |
| `DYNAMIC_ACCEPT_LANGUAGE` | `zh-TW,zh;q=0.9,en;q=0.8` | - | static/dynamic 請求使用的 Accept-Language |
| `DYNAMIC_VIEWPORT_WIDTH` | `1366` | px | dynamic browser viewport / screen 寬度 |
| `DYNAMIC_VIEWPORT_HEIGHT` | `768` | px | dynamic browser viewport / screen 高度 |
| `DYNAMIC_DEVICE_SCALE_FACTOR` | `1` | 倍 | dynamic browser device scale factor |
| `DYNAMIC_EXTRA_FLAGS` | `--disable-blink-features=AutomationControlled` | - | Chromium 啟動 flags，以 `\|` 分隔 |
| `USER_AGENT_ROTATION` | `true` | 布林值 | 是否每次 `/scrape` 請求隨機挑選 User-Agent |
| `USER_AGENTS` | (內建列表) | - | 自訂 User-Agent 池，以 `\|` 分隔；空白時使用內建列表 |
| `AUTO_MIN_HTML_LENGTH` | `1000` | 字元 | 靜態 HTML 少於此長度時，`auto` 模式改用動態抓取 |
| `EXTRA_JS_SIGNALS` | 空白 | - | 額外的 JavaScript 頁面辨識關鍵字，以 `\|` 分隔 |
| `AUTO_EXPAND_DEFAULT` | `true` | 布林值 | 是否預設啟動自動內容展開功能 |
| `AUTO_EXPAND_KEYWORDS` | (內建列表) | - | 觸發點擊的關鍵字列表，以 `\|` 分隔 |
| `AUTO_EXPAND_WAIT_TIMEOUT` | `15000` | 毫秒 | 等待展開按鍵出現的最長時間 |
| `AUTO_EXPAND_AFTER_CLICK_WAIT` | `1000` | 毫秒 | 點擊按鈕後，額外等待資料載入的時間 |
| `MAX_CLICK_SELECTORS` | `20` | 次 | 單次請求允許手動提供的 CSS Selector 數量上限 |
| `MAX_CLICKS_PER_SELECTOR` | `20` | 次 | 每個 Selector 最多連續點擊次數 |
| `MAX_INPUT_SELECTORS` | `20` | 個 | 單次請求允許提供的 `input_values` 數量上限 |
| `MAX_INPUT_VALUE_LENGTH` | `2000` | 字元 | 每個 `input_values` 值允許的最大長度 |
| `FORM_ACTION_TIMEOUT` | `15000` | 毫秒 | 填表單或等待 `wait_for_selector` 時，每個 selector 最長等待時間 |
| `MAX_WAIT_AFTER_ACTIONS` | `60000` | 毫秒 | 單次請求允許 `wait_after_actions` 等待的最大時間 |
| `CLEAN_CONTENT_DEFAULT` | `true` | 布林值 | 是否預設在 Markdownify 前清理 HTML |
| `CONTENT_SELECTORS` | (內建列表) | - | 自動挑選主體內容的 CSS Selector 候選，以 `\|` 分隔 |
| `CONTENT_MIN_TEXT_LENGTH` | `200` | 字元 | 主體候選節點至少要有多少文字才會被採用 |
| `REMOVE_TAGS` | (內建列表) | - | Markdownify 前一律刪除的 HTML tags，以 `\|` 分隔 |
| `REMOVE_SELECTORS` | (內建列表) | - | Markdownify 前一律刪除的 CSS Selectors，以 `\|` 分隔 |
| `MAX_CLEANING_SELECTORS` | `50` | 個 | 單次請求允許額外提供的 `remove_selectors` 數量上限 |

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
| `input_values` | 否 | `{}` | Dict[str, str] | dynamic 模式中要填入的表單欄位，key 為 CSS Selector，value 為填入內容 |
| `click_selectors` | 否 | `[]` | List[str] | 手動指定要點擊的 CSS Selectors |
| `wait_for_selector` | 否 | `null` | CSS Selector | 執行表單填寫與點擊後，等待指定元素出現再抓 HTML |
| `wait_after_actions` | 否 | `0` | 毫秒 | 執行表單填寫與點擊後額外等待多久，適合 WebSocket 或非同步結果頁 |
| `clean_content` | 否 | `true` | 布林值 | 是否在 Markdownify 前執行內容清理與主體萃取 |
| `content_selector` | 否 | `null` | CSS Selector | 手動指定要轉 Markdown 的主體節點 |
| `remove_selectors` | 否 | `[]` | List[str] | 單次請求額外要刪除的 CSS Selectors |

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
    "content_selector": "main article",
    "remove_selectors": [".ad-slot", ".related-jobs"],
    "response_format": "markdown"
  }'
```

### 表單互動範例

針對「進入頁面、填 input、點擊按鈕、等待結果」這類工具頁，可使用 `input_values` 搭配 `click_selectors`。例如 itdog HTTP 測速頁：

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{
    "url": "https://www.itdog.cn/http/",
    "mode": "dynamic",
    "input_values": {
      "#host": "https://example.com"
    },
    "click_selectors": [
      "button.btn-primary.ml-3.mb-3"
    ],
    "wait_after_actions": 30000,
    "clean_content": false,
    "response_format": "markdown"
  }'
```

如果目標頁面有穩定的結果節點，也可以用 `wait_for_selector` 取代固定等待：

```json
{
  "url": "https://www.itdog.cn/http/",
  "mode": "dynamic",
  "input_values": {
    "#host": "https://example.com"
  },
  "click_selectors": [
    "button[onclick=\"check_form('fast')\"]"
  ],
  "wait_for_selector": ".node_tr",
  "wait_after_actions": 5000,
  "response_format": "markdown"
}
```

## 抓取模式

### `auto`

一般使用建議選擇此模式。

1. 先使用 `AsyncFetcher` 進行靜態抓取。
2. 檢查 HTML 是否包含 JavaScript 提示關鍵字或長度是否過短。
3. **若請求內帶有 `input_values`、`click_selectors`、`wait_for_selector` 或 `wait_after_actions`**，或者命中上述條件，系統會自動切換為 `DynamicFetcher` 進行瀏覽器模擬。

### `static`

只使用 `AsyncFetcher`。

優點：速度極快、資源消耗最低。
限制：無法取得 JavaScript 渲染後的內容，且**不支援表單填寫或點擊模擬功能**。

### `dynamic`

直接使用 `DynamicFetcher` 啟動瀏覽器抓取。

優點：適合 104、myF5、以及任何需要執行 JS 點擊或等待資源載入的網站。
限制：速度較慢、資源消耗較高。

## 內容清理與主體萃取

系統預設會先清理 HTML，再交給 Markdownify。這可以大幅降低選單、頁尾、廣告、Cookie 提示、社群分享、推薦文章等噪音，避免輸出 Token 數爆表。

預設清理流程：

1. 移除註解、`script`、`style`、`nav`、`footer`、`aside`、`iframe`、表單與按鈕等節點。
2. 移除常見噪音 selector，例如 `.ads`、`.cookie-banner`、`.sidebar`、`.social-share`、`.related-posts`。
3. 從 `article`、`main`、`[role='main']`、`.entry-content` 等候選節點中挑出文字量最多的主體內容。
4. 將清理後的 HTML 轉成 Markdown，並壓縮多餘空白行。

單次請求可用 `content_selector` 精準指定主體，例如：

```json
{
  "url": "https://example.com/post",
  "content_selector": "article.post",
  "remove_selectors": [".author-box", ".related-posts"],
  "response_format": "markdown"
}
```

如果特殊網站需要完整原始 HTML 轉 Markdown，可傳入 `"clean_content": false` 關閉清理。

## Dynamic 併發與排隊控制

`dynamic` 模式會啟動無頭瀏覽器，CPU 與 RAM 成本比靜態抓取高很多。服務預設使用 `asyncio.Semaphore` 限制同時執行的 DynamicFetcher 數量，超過上限的請求會在 FastAPI process 內排隊等待。

預設設定：

```env
DYNAMIC_CONCURRENCY=2
DYNAMIC_QUEUE_TIMEOUT=120
```

行為說明：

1. 每個 dynamic 請求進入 `fetch_dynamic()` 時會先等待 semaphore。
2. 有名額才會真正呼叫 `DynamicFetcher.async_fetch()` 並啟動瀏覽器。
3. 如果等待超過 `DYNAMIC_QUEUE_TIMEOUT` 秒，API 會回傳 `503 Dynamic fetch queue timeout`。

小型 VPS 建議把 `DYNAMIC_CONCURRENCY` 設為 `1` 或 `2`。如果使用多個 Uvicorn worker 或多個容器副本，每個 process 都會有自己的 semaphore；需要跨 process 的全域限制時，應改用 Redis queue、Celery、RQ 或其他外部 worker queue。

## User-Agent 輪換與 Basic Stealth

本服務預設會在每次 `/scrape` 請求開始時，從 User-Agent 池挑選一個 `selected_user_agent`。這個選擇發生在 API 內部，不需要 n8n 或呼叫端提供瀏覽器特徵。

```text
n8n / client -> POST /scrape
              -> scrapling-api 隨機挑選 User-Agent
              -> static / dynamic 抓取沿用同一個 User-Agent
              -> 目標網站看到的是 API 選出的 User-Agent
```

`auto` 模式若先用 static 抓取，後來 fallback 到 dynamic，兩次抓取會沿用同一個 User-Agent，避免同一個請求看起來像不同瀏覽器。

預設設定：

```env
USER_AGENT_ROTATION=true
USER_AGENTS=
```

`USER_AGENTS` 留空時會使用 `main.py` 內建的少量現代桌面瀏覽器 User-Agent。若要自訂，多個 UA 使用 `|` 分隔。

dynamic 模式還可啟用 basic stealth：

```env
DYNAMIC_STEALTH_BASIC=true
DYNAMIC_LOCALE=zh-TW
DYNAMIC_TIMEZONE=Asia/Taipei
DYNAMIC_ACCEPT_LANGUAGE=zh-TW,zh;q=0.9,en;q=0.8
DYNAMIC_VIEWPORT_WIDTH=1366
DYNAMIC_VIEWPORT_HEIGHT=768
DYNAMIC_DEVICE_SCALE_FACTOR=1
DYNAMIC_EXTRA_FLAGS=--disable-blink-features=AutomationControlled
```

basic stealth 會做以下低成本強化：

1. 將選出的 User-Agent 傳入 `DynamicFetcher.async_fetch(useragent=...)`。
2. 將 `Accept-Language` 與 `locale` 對齊。
3. 設定 `timezone_id`，避免瀏覽器時區與語系不一致。
4. 設定 viewport、screen、device scale、mobile/touch 狀態。
5. 加入 Chromium flag `--disable-blink-features=AutomationControlled`。
6. 在頁面載入前注入 script，讓 `navigator.webdriver` 回傳 `undefined`。

這不是 Captcha solver，也不會保證繞過進階反爬。它的目標是降低常見自動化破綻；如果目標站檢查 Canvas、WebGL、TLS fingerprint、IP reputation 或行為軌跡，仍需要進一步使用 StealthyFetcher、proxy/session 策略或人工授權流程。

## Dynamic 表單互動、內容展開與點擊模擬

本服務專門為「抓取完整文章」與「操作工具頁後抓結果」設計了互動機制：

- **表單填寫**：透過 `input_values` 在 dynamic 模式中先填入指定 input / textarea，例如 `{"#host": "https://example.com"}`。
- **自動展開**：會尋找頁面中符合關鍵字（如 `show more`, `read more`, `applies to`）且具備屬性 `aria-expanded="false"` 的按鈕自動點擊。
- **手動點擊**：透過 `click_selectors` 參數，你可以精準控制瀏覽器點擊特定的 UI 元素（例如多個分頁標籤、載入更多按鈕等）。
- **等待結果**：透過 `wait_for_selector` 等待結果節點出現，或用 `wait_after_actions` 在動作後固定等待一段時間，適合 WebSocket 或非同步載入頁。
- **流程保護**：系統會透過 `MAX_CLICKS_PER_SELECTOR` 與超時機制保護，防止網頁因異常 Selector 導致無限點擊或佔用過多資源。

互動順序固定為：

```text
input_values -> auto_expand -> click_selectors -> wait_for_selector -> wait_after_actions -> read HTML
```

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
