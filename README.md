Dockerfile 的作用：

FROM pyd4vinci/scrapling以 Scrapling 官方映像為基底，內含爬蟲與瀏覽器執行環境。

WORKDIR /service將容器內工作目錄設為 /service。

RUN python -m pip install --no-cache-dir "scrapling[all]" fastapi "uvicorn[standard]" markdownify安裝完整 Scrapling、FastAPI、Uvicorn 與 HTML 轉 Markdown 套件。

COPY main.py .把主程式複製到容器內，因此修改 main.py 後必須重新 build image。

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]清除基底映像原本的 ENTRYPOINT，並啟動 FastAPI，監聽容器內的 8080 Port。

docker-compose.yml 的作用：

• build: .：使用目前目錄的 Dockerfile 建立 image。
• container_name: scrapling-api：容器名稱固定為 scrapling-api。
• restart: unless-stopped：主機重開或程式異常時自動重啟，除非你手動停止。
• env_file: .env：把 .env 內容注入容器，這就是 main.py 能讀到 API_KEY 的原因。
• ports: 8080:8080：將主機 8080 Port 對應到容器 8080 Port。

從零部署指令

將 4 個檔案放在同一個資料夾：

scrapling-api/
├── Dockerfile
├── docker-compose.yml
├── main.py
└── .env先修改 .env：

API_KEY=換成長隨機密鑰
DYNAMIC_TIMEOUT=60000第一次建立並啟動：

cd ~/scrapling-api
docker compose up -d --build確認容器狀態：

docker compose ps
docker logs --tail=100 scrapling-api
curl http://localhost:8080/health停止：

docker compose down只修改 .env 後，不用重新 build，但要重新建立容器：

docker compose up -d --force-recreate修改 main.py、Dockerfile 後，需要重新 build：

docker compose up -d --build完全不使用快取重建，只有遇到依賴安裝問題時才需要：

docker compose build --no-cache
docker compose up -d前面 API 呼叫、auto/static/dynamic、n8n 與 Cloudflared 的教學仍然適用；缺少的是這段 Docker 部署說明。
