import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from markdownify import markdownify as md
from pydantic import BaseModel, Field, HttpUrl
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
MAX_CLICK_SELECTORS = env_int("MAX_CLICK_SELECTORS", 20)
MAX_CLICKS_PER_SELECTOR = env_int("MAX_CLICKS_PER_SELECTOR", 20)

AUTO_EXPAND_SELECTOR = (
    "main button[aria-expanded='false'], "
    "main [role='button'][aria-expanded='false'], "
    "article button[aria-expanded='false'], "
    "article [role='button'][aria-expanded='false']"
)

AUTO_EXPAND_KEYWORDS = [
    "applies to",
    "details",
    "expand",
    "load more",
    "read more",
    "see more",
    "show more",
    "view more",
]

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
    auto_expand: bool = True
    click_selectors: list[str] = Field(default_factory=list)


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


async def click_visible_elements(page, selector: str) -> int:
    clicked = 0
    elements = await page.locator(selector).all()

    for element in elements[:MAX_CLICKS_PER_SELECTOR]:
        if await element.is_visible():
            await element.click()
            clicked += 1

    return clicked


async def expand_common_content(page) -> int:
    clicked = await click_visible_elements(page, "main details:not([open]) > summary")

    try:
        await page.locator(AUTO_EXPAND_SELECTOR).first.wait_for(
            state="visible",
            timeout=15000,
        )
    except Exception:
        return clicked

    elements = await page.locator(AUTO_EXPAND_SELECTOR).all()

    for element in elements[:MAX_CLICKS_PER_SELECTOR]:
        if not await element.is_visible():
            continue

        text = (await element.inner_text()).strip().lower()
        aria_label = (await element.get_attribute("aria-label") or "").strip().lower()
        label = f"{text} {aria_label}"

        if any(keyword in label for keyword in AUTO_EXPAND_KEYWORDS):
            await element.click()
            clicked += 1

    return clicked


async def fetch_dynamic(url: str, auto_expand: bool, click_selectors: list[str]):
    async def interact_with_page(page):
        clicked = 0

        if auto_expand:
            clicked += await expand_common_content(page)

        for selector in click_selectors:
            clicked += await click_visible_elements(page, selector)

        if clicked:
            await page.wait_for_timeout(1000)

    page = await DynamicFetcher.async_fetch(
        url,
        headless=True,
        timeout=DYNAMIC_TIMEOUT,
        network_idle=DYNAMIC_NETWORK_IDLE,
        wait=DYNAMIC_WAIT,
        disable_resources=DYNAMIC_DISABLE_RESOURCES,
        page_action=interact_with_page,
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
    click_selectors = [selector.strip() for selector in req.click_selectors if selector.strip()]

    if mode not in {"auto", "static", "dynamic"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if response_format not in {"json", "markdown"}:
        raise HTTPException(status_code=400, detail="Invalid response_format")

    if len(click_selectors) > MAX_CLICK_SELECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many click_selectors; maximum is {MAX_CLICK_SELECTORS}",
        )

    if mode == "static" and (req.auto_expand or click_selectors):
        raise HTTPException(
            status_code=400,
            detail="auto_expand and click_selectors require auto or dynamic mode",
        )

    try:
        if mode == "dynamic":
            status, html, used_mode = await fetch_dynamic(
                url,
                req.auto_expand,
                click_selectors,
            )
        else:
            status, html, used_mode = await fetch_static(url)

            if mode == "auto" and (should_use_dynamic(html) or click_selectors):
                status, html, used_mode = await fetch_dynamic(
                    url,
                    req.auto_expand,
                    click_selectors,
                )

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
