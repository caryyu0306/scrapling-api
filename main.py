import asyncio
import os
import re

from bs4 import BeautifulSoup, Comment
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


def env_list(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split("|") if item.strip()]


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
DYNAMIC_CONCURRENCY = env_int("DYNAMIC_CONCURRENCY", 2)
DYNAMIC_QUEUE_TIMEOUT = env_int("DYNAMIC_QUEUE_TIMEOUT", 120)

if DYNAMIC_CONCURRENCY < 1:
    raise RuntimeError("DYNAMIC_CONCURRENCY must be at least 1")

if DYNAMIC_QUEUE_TIMEOUT < 1:
    raise RuntimeError("DYNAMIC_QUEUE_TIMEOUT must be at least 1")

dynamic_semaphore = asyncio.Semaphore(DYNAMIC_CONCURRENCY)

AUTO_MIN_HTML_LENGTH = env_int("AUTO_MIN_HTML_LENGTH", 1000)
AUTO_EXPAND_DEFAULT = env_bool("AUTO_EXPAND_DEFAULT", True)
AUTO_EXPAND_WAIT_TIMEOUT = env_int("AUTO_EXPAND_WAIT_TIMEOUT", 15000)
AUTO_EXPAND_AFTER_CLICK_WAIT = env_int("AUTO_EXPAND_AFTER_CLICK_WAIT", 1000)
MAX_CLICK_SELECTORS = env_int("MAX_CLICK_SELECTORS", 20)
MAX_CLICKS_PER_SELECTOR = env_int("MAX_CLICKS_PER_SELECTOR", 20)

CLEAN_CONTENT_DEFAULT = env_bool("CLEAN_CONTENT_DEFAULT", True)
MAX_CLEANING_SELECTORS = env_int("MAX_CLEANING_SELECTORS", 50)
CONTENT_MIN_TEXT_LENGTH = env_int("CONTENT_MIN_TEXT_LENGTH", 200)

DEFAULT_CONTENT_SELECTORS = (
    "article|main|[role='main']|#content|#main-content|.content|.main-content|"
    ".post-content|.entry-content|.article-content"
)

CONTENT_SELECTORS = env_list("CONTENT_SELECTORS", DEFAULT_CONTENT_SELECTORS)

DEFAULT_REMOVE_TAGS = (
    "script|style|noscript|template|nav|footer|aside|iframe|svg|canvas|form|"
    "input|select|textarea|button"
)

REMOVE_TAGS = env_list("REMOVE_TAGS", DEFAULT_REMOVE_TAGS)

DEFAULT_REMOVE_SELECTORS = (
    "[role='navigation']|[role='banner']|[role='contentinfo']|[aria-hidden='true']|"
    ".ad|.ads|.advertisement|.banner|.cookie|.cookie-banner|.cookies|.footer|"
    ".menu|.nav|.navbar|.newsletter|.popup|.sidebar|.social-share|"
    ".subscribe|.related-posts|.recommended|#ad|#ads|#footer|#header|#nav|#sidebar"
)

REMOVE_SELECTORS = env_list("REMOVE_SELECTORS", DEFAULT_REMOVE_SELECTORS)

DEFAULT_AUTO_EXPAND_SELECTOR = (
    "main button[aria-expanded='false'], "
    "main [role='button'][aria-expanded='false'], "
    "article button[aria-expanded='false'], "
    "article [role='button'][aria-expanded='false']"
)

AUTO_EXPAND_SELECTOR = os.getenv(
    "AUTO_EXPAND_SELECTOR",
    DEFAULT_AUTO_EXPAND_SELECTOR,
)

DEFAULT_AUTO_EXPAND_KEYWORDS = (
    "applies to|details|expand|load more|read more|see more|show more|view more"
)

AUTO_EXPAND_KEYWORDS = [
    keyword.strip().lower()
    for keyword in os.getenv(
        "AUTO_EXPAND_KEYWORDS",
        DEFAULT_AUTO_EXPAND_KEYWORDS,
    ).split("|")
    if keyword.strip()
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
    auto_expand: bool = AUTO_EXPAND_DEFAULT
    click_selectors: list[str] = Field(default_factory=list)
    clean_content: bool = CLEAN_CONTENT_DEFAULT
    content_selector: str | None = None
    remove_selectors: list[str] = Field(default_factory=list)


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
            timeout=AUTO_EXPAND_WAIT_TIMEOUT,
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
            await page.wait_for_timeout(AUTO_EXPAND_AFTER_CLICK_WAIT)

    try:
        await asyncio.wait_for(
            dynamic_semaphore.acquire(),
            timeout=DYNAMIC_QUEUE_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail="Dynamic fetch queue timeout",
        ) from exc

    try:
        page = await DynamicFetcher.async_fetch(
            url,
            headless=True,
            timeout=DYNAMIC_TIMEOUT,
            network_idle=DYNAMIC_NETWORK_IDLE,
            wait=DYNAMIC_WAIT,
            disable_resources=DYNAMIC_DISABLE_RESOURCES,
            page_action=interact_with_page,
        )
    finally:
        dynamic_semaphore.release()

    html = page.body.decode("utf-8", errors="ignore")
    return page.status, html, "dynamic"


def should_use_dynamic(html: str) -> bool:
    text = html.lower()

    if any(signal in text for signal in JS_SIGNALS):
        return True

    if len(html.strip()) < AUTO_MIN_HTML_LENGTH:
        return True

    return False


def remove_matching_selectors(soup: BeautifulSoup, selectors: list[str]) -> None:
    for selector in selectors:
        try:
            for element in soup.select(selector):
                element.decompose()
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid remove selector: {selector}",
            ) from exc


def pick_content_root(soup: BeautifulSoup, content_selector: str | None):
    if content_selector:
        try:
            matches = soup.select(content_selector)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content_selector: {content_selector}",
            ) from exc

        if not matches:
            raise HTTPException(
                status_code=400,
                detail=f"content_selector did not match anything: {content_selector}",
            )

        return matches[0]

    candidates = []
    for selector in CONTENT_SELECTORS:
        try:
            candidates.extend(soup.select(selector))
        except Exception:
            continue

    best = None
    best_length = 0
    for candidate in candidates:
        text_length = len(candidate.get_text(" ", strip=True))
        if text_length > best_length:
            best = candidate
            best_length = text_length

    if best is not None and best_length >= CONTENT_MIN_TEXT_LENGTH:
        return best

    return soup.body or soup


def clean_html_for_markdown(
    html: str,
    content_selector: str | None,
    remove_selectors: list[str],
) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag_name in REMOVE_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    remove_matching_selectors(soup, REMOVE_SELECTORS + remove_selectors)
    content_root = pick_content_root(soup, content_selector)

    return str(content_root)


def distill_markdown(markdown: str) -> str:
    markdown = "\n".join(line.rstrip() for line in markdown.splitlines())
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


@app.post("/scrape")
async def scrape(req: ScrapeRequest, x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    url = str(req.url)
    mode = req.mode.lower()
    response_format = req.response_format.lower()
    click_selectors = [selector.strip() for selector in req.click_selectors if selector.strip()]
    remove_selectors = [
        selector.strip()
        for selector in req.remove_selectors
        if selector.strip()
    ]

    if mode not in {"auto", "static", "dynamic"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if response_format not in {"json", "markdown"}:
        raise HTTPException(status_code=400, detail="Invalid response_format")

    if len(click_selectors) > MAX_CLICK_SELECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many click_selectors; maximum is {MAX_CLICK_SELECTORS}",
        )

    if len(remove_selectors) > MAX_CLEANING_SELECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many remove_selectors; maximum is {MAX_CLEANING_SELECTORS}",
        )

    if mode == "static" and click_selectors:
        raise HTTPException(
            status_code=400,
            detail="click_selectors require auto or dynamic mode",
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

        markdown_html = html
        if req.clean_content:
            markdown_html = clean_html_for_markdown(
                html,
                req.content_selector,
                remove_selectors,
            )

        markdown = distill_markdown(md(markdown_html))

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
