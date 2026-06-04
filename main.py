import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from markdownify import markdownify as md
from pydantic import BaseModel, HttpUrl
from scrapling.fetchers import AsyncFetcher, DynamicFetcher

app = FastAPI()


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise RuntimeError(f"{name} must be true or false")


API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY is required")

STATIC_TIMEOUT = env_int("STATIC_TIMEOUT", 20)
STATIC_RETRIES = env_int("STATIC_RETRIES", 2)
STATIC_STEALTHY_HEADERS = env_bool("STATIC_STEALTHY_HEADERS", True)

DYNAMIC_TIMEOUT = env_int("DYNAMIC_TIMEOUT", 60000)
DYNAMIC_WAIT = env_int("DYNAMIC_WAIT", 5000)
DYNAMIC_NETWORK_IDLE = env_bool("DYNAMIC_NETWORK_IDLE", True)
DYNAMIC_DISABLE_RESOURCES = env_bool("DYNAMIC_DISABLE_RESOURCES", False)

AUTO_MIN_HTML_LENGTH = env_int("AUTO_MIN_HTML_LENGTH", 1000)

DEFAULT_JS_SIGNALS = [
    "doesn't work properly without javascript",
    "enable javascript",
    "please enable javascript",
    'id="app"',
    "id='app'",
    "vue-start",
    "css error",
    "sorry to interrupt",
]

EXTRA_JS_SIGNALS = [
    signal.strip().lower()
    for signal in os.getenv("EXTRA_JS_SIGNALS", "").split("|")
    if signal.strip()
]

JS_SIGNALS = DEFAULT_JS_SIGNALS + EXTRA_JS_SIGNALS


class ScrapeRequest(BaseModel):
    url: HttpUrl
    mode: str = "auto"  # auto / static / dynamic
    response_format: str = "json"  # json / markdown


@app.get("/health")
def health():
    return {"ok": True}


async def fetch_static(url: str):
    page = await AsyncFetcher.get(
        url,
        timeout=STATIC_TIMEOUT,
        retries=STATIC_RETRIES,
        stealthy_headers=STATIC_STEALTHY_HEADERS,
    )

    html = page.body.decode("utf-8", errors="ignore")
    return page.status, html, "static"


async def fetch_dynamic(url: str):
    page = await DynamicFetcher.async_fetch(
        url,
        headless=True,
        timeout=DYNAMIC_TIMEOUT,
        network_idle=DYNAMIC_NETWORK_IDLE,
        wait=DYNAMIC_WAIT,
        disable_resources=DYNAMIC_DISABLE_RESOURCES,
    )

    html = page.body.decode("utf-8", errors="ignore")
    return page.status, html, "dynamic"


def should_use_dynamic(html: str) -> bool:
    text = html.lower()

    if any(signal in text for signal in JS_SIGNALS):
        return True

    if len(html.strip()) < AUTO_MIN_HTML_LENGTH:
        return True

    return False


@app.post("/scrape")
async def scrape(req: ScrapeRequest, x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    url = str(req.url)
    mode = req.mode.lower()
    response_format = req.response_format.lower()

    if mode not in {"auto", "static", "dynamic"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if response_format not in {"json", "markdown"}:
        raise HTTPException(status_code=400, detail="Invalid response_format")

    try:
        if mode == "dynamic":
            status, html, used_mode = await fetch_dynamic(url)
        else:
            status, html, used_mode = await fetch_static(url)

            if mode == "auto" and should_use_dynamic(html):
                status, html, used_mode = await fetch_dynamic(url)

        markdown = md(html)

        if response_format == "markdown":
            return PlainTextResponse(
                markdown,
                media_type="text/markdown; charset=utf-8",
            )

        return {
            "success": True,
            "url": url,
            "status": status,
            "mode": used_mode,
            "markdown": markdown,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
