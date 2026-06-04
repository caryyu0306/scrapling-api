# Scrapling API

使用 FastAPI 與 Scrapling 建立的網頁抓取 API，可將目標網頁的 HTML 轉換為 Markdown。

此服務支援靜態抓取、JavaScript 動態頁面抓取，以及自動判斷模式，適合提供給 n8n、內部工具或其他程式呼叫。

## 功能特色

- 支援靜態頁面與 JavaScript 動態頁面
- `auto` 模式會先嘗試靜態抓取，必要時自動切換為動態抓取
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
    +-- mode=dynamic ----> DynamicFetcher
    |
    +-- mode=auto
          |
          +-- 先使用 AsyncFetcher
          |
          +-- 判斷為 JavaScript 空殼頁或內容過短
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

RUN python -m pip install --no-cache-dir "scrapling[all]" fastapi "uvicorn[standard]" markdownify

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

布林值可使用：

```text
true / false
1 / 0
yes / no
on / off
```

### 建議設定

一般網站：

```env
DYNAMIC_TIMEOUT=30000
DYNAMIC_WAIT=2000
```

104、myF5 等動態網站：

```env
DYNAMIC_TIMEOUT=60000
DYNAMIC_WAIT=5000
DYNAMIC_DISABLE_RESOURCES=false
```

很慢的網站：

```env
DYNAMIC_TIMEOUT=90000
```

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
| `mode` | 否 | `auto` | `auto`、`static`、`dynamic` | 抓取模式 |
| `response_format` | 否 | `json` | `json`、`markdown` | 回應格式 |

### 回傳 Markdown

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{"url":"https://www.104.com.tw/job/7rnd9","mode":"auto","response_format":"markdown"}'
```

### 回傳 JSON

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{"url":"https://example.com","mode":"auto","response_format":"json"}'
```

JSON 回應範例：

```json
{
  "success": true,
  "url": "https://example.com/",
  "status": 200,
  "mode": "static",
  "markdown": "..."
}
```

回應中的 `mode` 代表最後實際使用的抓取模式。

## 抓取模式

### `auto`

一般使用建議選擇此模式。

1. 先使用 `AsyncFetcher` 進行靜態抓取。
2. 檢查 HTML 是否像 JavaScript 空殼頁。
3. 如果命中辨識關鍵字，或 HTML 長度少於 `AUTO_MIN_HTML_LENGTH`，改用 `DynamicFetcher`。

### `static`

只使用 `AsyncFetcher`。

優點：

- 速度快
- 資源消耗低
- 適合一般靜態網站

限制：

- 無法取得需要 JavaScript 渲染後才出現的內容

### `dynamic`

直接使用 `DynamicFetcher` 啟動瀏覽器抓取。

優點：

- 適合 104、myF5 等 JavaScript 動態網站
- 可等待頁面資源與動態內容載入

限制：

- 速度較慢
- CPU 與記憶體使用量較高

> 此版本的流程是「靜態判斷一次，必要時完整動態抓取一次」，沒有 `dynamic_fast` 或 `dynamic_full` 兩段式流程。

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

遇到新的網站提示文字時，可在 `.env` 加入額外關鍵字：

```env
EXTRA_JS_SIGNALS=javascript required|please turn on javascript|app loading failed
```

注意事項：

- 多個關鍵字使用 `|` 分隔
- 比對不分大小寫
- 不建議使用逗號分隔，因為網站文字本身可能包含逗號

如果靜態頁面仍未被辨識為 JavaScript 空殼頁，可以：

1. 將該頁面的特有提示文字加入 `EXTRA_JS_SIGNALS`
2. 適度提高 `AUTO_MIN_HTML_LENGTH`
3. 呼叫 API 時直接指定 `"mode":"dynamic"`

## 容器維護

### 查看狀態

```bash
docker compose ps
```

### 查看日誌

```bash
docker logs --tail=100 scrapling-api
```

即時追蹤日誌：

```bash
docker logs -f scrapling-api
```

### 停止服務

```bash
docker compose down
```

### 修改 `.env` 後套用設定

只修改 `.env` 時，不需要重新建立 image，但必須重新建立容器，環境變數才會重新載入。

```bash
docker compose up -d --force-recreate
```

### 修改 `main.py` 或 `Dockerfile` 後重新建立

`Dockerfile` 使用 `COPY main.py .`，因此修改 `main.py` 後必須重新 build。

```bash
docker compose up -d --build
```

### 不使用快取重新建立

只有遇到依賴安裝或 image 快取問題時，才建議使用：

```bash
docker compose build --no-cache
docker compose up -d
```

## 本機直接執行

若不使用 Docker，需要自行安裝 FastAPI、Uvicorn、Markdownify、Pydantic、Scrapling，以及 `DynamicFetcher` 所需的瀏覽器元件。

`main.py` 不會自行載入 `.env`，啟動 Uvicorn 時必須指定 `--env-file`：

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --env-file .env
```

## 常見問題

### `401 Invalid API key`

原因：請求 Header 的 `x-api-key` 與 `.env` 中的 `API_KEY` 不一致。

處理方式：

```bash
curl -H "x-api-key: YOUR_API_KEY" ...
```

### `400 Invalid mode`

`mode` 只能使用：

```text
auto
static
dynamic
```

### `400 Invalid response_format`

`response_format` 只能使用：

```text
json
markdown
```

### `API_KEY is required` 或容器一直重啟

原因：程式啟動時沒有讀到 `API_KEY`。

檢查項目：

1. `.env` 是否與 `docker-compose.yml` 位於同一個目錄
2. `docker-compose.yml` 是否包含 `env_file: .env`
3. `.env` 是否設定非空白的 `API_KEY`

修改後重新建立容器：

```bash
docker compose up -d --force-recreate
```

### `ModuleNotFoundError: No module named 'curl_cffi'`

原因：Scrapling 的完整依賴沒有安裝，或 image 使用了舊快取。

處理方式：

```bash
docker compose build --no-cache
docker compose up -d
```

### `auto` 模式回傳 `CSS Error`、`Loading` 或 JavaScript 提示

處理方式：

1. 將頁面特有文字加入 `EXTRA_JS_SIGNALS`
2. 提高 `AUTO_MIN_HTML_LENGTH`
3. 直接使用 `"mode":"dynamic"`
4. 確認 `DYNAMIC_DISABLE_RESOURCES=false`

### 動態頁面抓取逾時

將 `.env` 調整為：

```env
DYNAMIC_TIMEOUT=60000
DYNAMIC_WAIT=5000
```

很慢的網站可嘗試：

```env
DYNAMIC_TIMEOUT=90000
```


