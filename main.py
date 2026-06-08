import asyncio
import os
import random
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


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


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
    if not value.strip():
        value = default

    return [item.strip() for item in value.split("|") if item.strip()]


def env_optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    return value.strip() or None


API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY is required")

SCRAPLING_PROXY = env_optional("SCRAPLING_PROXY")
ALLOW_REQUEST_PROXY = env_bool("ALLOW_REQUEST_PROXY", True)

STATIC_TIMEOUT = env_int("STATIC_TIMEOUT", 20)
STATIC_RETRIES = env_int("STATIC_RETRIES", 2)
STATIC_STEALTHY_HEADERS = env_bool("STATIC_STEALTHY_HEADERS", True)

DYNAMIC_TIMEOUT = env_int("DYNAMIC_TIMEOUT", 60000)
DYNAMIC_WAIT = env_int("DYNAMIC_WAIT", 5000)
DYNAMIC_NETWORK_IDLE = env_bool("DYNAMIC_NETWORK_IDLE", True)
DYNAMIC_DISABLE_RESOURCES = env_bool("DYNAMIC_DISABLE_RESOURCES", False)
DYNAMIC_CONCURRENCY = env_int("DYNAMIC_CONCURRENCY", 2)
DYNAMIC_QUEUE_TIMEOUT = env_int("DYNAMIC_QUEUE_TIMEOUT", 120)
DYNAMIC_STEALTH_BASIC = env_bool("DYNAMIC_STEALTH_BASIC", True)
DYNAMIC_LOCALE = os.getenv("DYNAMIC_LOCALE", "zh-TW")
DYNAMIC_TIMEZONE = os.getenv("DYNAMIC_TIMEZONE", "Asia/Taipei")
DYNAMIC_ACCEPT_LANGUAGE = os.getenv(
    "DYNAMIC_ACCEPT_LANGUAGE",
    "zh-TW,zh;q=0.9,en;q=0.8",
)
DYNAMIC_VIEWPORT_WIDTH = env_int("DYNAMIC_VIEWPORT_WIDTH", 1366)
DYNAMIC_VIEWPORT_HEIGHT = env_int("DYNAMIC_VIEWPORT_HEIGHT", 768)
DYNAMIC_DEVICE_SCALE_FACTOR = env_float("DYNAMIC_DEVICE_SCALE_FACTOR", 1.0)
DYNAMIC_EXTRA_FLAGS = env_list(
    "DYNAMIC_EXTRA_FLAGS",
    "--disable-blink-features=AutomationControlled",
)

if DYNAMIC_CONCURRENCY < 1:
    raise RuntimeError("DYNAMIC_CONCURRENCY must be at least 1")

if DYNAMIC_QUEUE_TIMEOUT < 1:
    raise RuntimeError("DYNAMIC_QUEUE_TIMEOUT must be at least 1")

dynamic_semaphore = asyncio.Semaphore(DYNAMIC_CONCURRENCY)

DEFAULT_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36|"
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36|"
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36|"
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15|"
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
    "Gecko/20100101 Firefox/140.0"
)

USER_AGENT_ROTATION = env_bool("USER_AGENT_ROTATION", True)
USER_AGENTS = env_list("USER_AGENTS", DEFAULT_USER_AGENTS)

AUTO_MIN_HTML_LENGTH = env_int("AUTO_MIN_HTML_LENGTH", 1000)
AUTO_EXPAND_DEFAULT = env_bool("AUTO_EXPAND_DEFAULT", True)
AUTO_EXPAND_WAIT_TIMEOUT = env_int("AUTO_EXPAND_WAIT_TIMEOUT", 15000)
AUTO_EXPAND_AFTER_CLICK_WAIT = env_int("AUTO_EXPAND_AFTER_CLICK_WAIT", 1000)
MAX_CLICK_SELECTORS = env_int("MAX_CLICK_SELECTORS", 20)
MAX_CLICKS_PER_SELECTOR = env_int("MAX_CLICKS_PER_SELECTOR", 20)
MAX_INPUT_SELECTORS = env_int("MAX_INPUT_SELECTORS", 20)
MAX_INPUT_VALUE_LENGTH = env_int("MAX_INPUT_VALUE_LENGTH", 2000)
FORM_ACTION_TIMEOUT = env_int("FORM_ACTION_TIMEOUT", 15000)
MAX_WAIT_AFTER_ACTIONS = env_int("MAX_WAIT_AFTER_ACTIONS", 60000)

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
    proxy: str | None = None
    auto_expand: bool = AUTO_EXPAND_DEFAULT
    input_values: dict[str, str] = Field(default_factory=dict)
    click_selectors: list[str] = Field(default_factory=list)
    wait_for_selector: str | None = None
    wait_after_actions: int = 0
    clean_content: bool = CLEAN_CONTENT_DEFAULT
    content_selector: str | None = None
    remove_selectors: list[str] = Field(default_factory=list)


@app.get("/health")
def health():
    return {"ok": True}


def choose_user_agent() -> str | None:
    if not USER_AGENT_ROTATION or not USER_AGENTS:
        return None

    return random.choice(USER_AGENTS)


def build_request_headers(user_agent: str | None) -> dict[str, str] | None:
    headers = {}

    if user_agent:
        headers["User-Agent"] = user_agent

    if DYNAMIC_STEALTH_BASIC and DYNAMIC_ACCEPT_LANGUAGE:
        headers["Accept-Language"] = DYNAMIC_ACCEPT_LANGUAGE

    return headers or None


def build_dynamic_additional_args() -> dict:
    if not DYNAMIC_STEALTH_BASIC:
        return {}

    return {
        "viewport": {
            "width": DYNAMIC_VIEWPORT_WIDTH,
            "height": DYNAMIC_VIEWPORT_HEIGHT,
        },
        "screen": {
            "width": DYNAMIC_VIEWPORT_WIDTH,
            "height": DYNAMIC_VIEWPORT_HEIGHT,
        },
        "device_scale_factor": DYNAMIC_DEVICE_SCALE_FACTOR,
        "is_mobile": False,
        "has_touch": False,
        "color_scheme": "light",
    }


async def setup_stealth_page(page) -> None:
    if not DYNAMIC_STEALTH_BASIC:
        return

    await page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        """
    )


def select_proxy(request_proxy: str | None) -> str | None:
    proxy = request_proxy.strip() if request_proxy else None
    if proxy and not ALLOW_REQUEST_PROXY:
        raise HTTPException(
            status_code=400,
            detail="Request body proxy is disabled by ALLOW_REQUEST_PROXY",
        )

    return proxy or SCRAPLING_PROXY


async def fetch_static(url: str, user_agent: str | None, proxy: str | None):
    page = await AsyncFetcher.get(
        url,
        timeout=STATIC_TIMEOUT,
        retries=STATIC_RETRIES,
        stealthy_headers=STATIC_STEALTHY_HEADERS,
        headers=build_request_headers(user_agent),
        proxy=proxy,
    )

    html = page.body.decode("utf-8", errors="ignore")
    return page.status, html, "static"


async def click_visible_elements(page, selector: str) -> int:
    clicked = 0
    try:
        elements = await page.locator(selector).all()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid click selector: {selector}",
        ) from exc

    for element in elements[:MAX_CLICKS_PER_SELECTOR]:
        if await element.is_visible():
            await element.click()
            clicked += 1

    return clicked


async def fill_input_values(page, input_values: dict[str, str]) -> int:
    filled = 0

    for selector, value in input_values.items():
        try:
            target = page.locator(selector).first
            await target.wait_for(state="visible", timeout=FORM_ACTION_TIMEOUT)
            await target.fill(value)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid or unavailable input selector: {selector}",
            ) from exc

        filled += 1

    return filled


async def wait_for_dynamic_selector(page, selector: str) -> None:
    try:
        await page.locator(selector).first.wait_for(
            state="visible",
            timeout=FORM_ACTION_TIMEOUT,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"wait_for_selector did not appear: {selector}",
        ) from exc


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


async def fetch_dynamic(
    url: str,
    auto_expand: bool,
    input_values: dict[str, str],
    click_selectors: list[str],
    wait_for_selector: str | None,
    wait_after_actions: int,
    user_agent: str | None,
    proxy: str | None,
):
    async def interact_with_page(page):
        filled = await fill_input_values(page, input_values)
        clicked = 0

        if auto_expand:
            clicked += await expand_common_content(page)

        for selector in click_selectors:
            clicked += await click_visible_elements(page, selector)

        if wait_for_selector:
            await wait_for_dynamic_selector(page, wait_for_selector)

        if wait_after_actions:
            await page.wait_for_timeout(wait_after_actions)
        elif clicked or filled:
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
            useragent=user_agent,
            locale=DYNAMIC_LOCALE if DYNAMIC_STEALTH_BASIC else None,
            timezone_id=DYNAMIC_TIMEZONE if DYNAMIC_STEALTH_BASIC else None,
            extra_headers=build_request_headers(None),
            proxy=proxy,
            extra_flags=DYNAMIC_EXTRA_FLAGS if DYNAMIC_STEALTH_BASIC else None,
            additional_args=build_dynamic_additional_args(),
            timeout=DYNAMIC_TIMEOUT,
            network_idle=DYNAMIC_NETWORK_IDLE,
            wait=DYNAMIC_WAIT,
            disable_resources=DYNAMIC_DISABLE_RESOURCES,
            page_setup=setup_stealth_page if DYNAMIC_STEALTH_BASIC else None,
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
    input_values = {
        selector.strip(): value
        for selector, value in req.input_values.items()
        if selector.strip()
    }
    click_selectors = [selector.strip() for selector in req.click_selectors if selector.strip()]
    wait_for_selector = (
        req.wait_for_selector.strip()
        if req.wait_for_selector and req.wait_for_selector.strip()
        else None
    )
    wait_after_actions = req.wait_after_actions
    remove_selectors = [
        selector.strip()
        for selector in req.remove_selectors
        if selector.strip()
    ]
    needs_dynamic_interaction = bool(
        input_values
        or click_selectors
        or wait_for_selector
        or wait_after_actions
    )

    if mode not in {"auto", "static", "dynamic"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if response_format not in {"json", "markdown"}:
        raise HTTPException(status_code=400, detail="Invalid response_format")

    if len(input_values) > MAX_INPUT_SELECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many input_values; maximum is {MAX_INPUT_SELECTORS}",
        )

    for selector, value in input_values.items():
        if len(value) > MAX_INPUT_VALUE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"input value for {selector} is too long; "
                    f"maximum is {MAX_INPUT_VALUE_LENGTH}"
                ),
            )

    if len(click_selectors) > MAX_CLICK_SELECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many click_selectors; maximum is {MAX_CLICK_SELECTORS}",
        )

    if wait_after_actions < 0 or wait_after_actions > MAX_WAIT_AFTER_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "wait_after_actions must be between 0 and "
                f"{MAX_WAIT_AFTER_ACTIONS} milliseconds"
            ),
        )

    if len(remove_selectors) > MAX_CLEANING_SELECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many remove_selectors; maximum is {MAX_CLEANING_SELECTORS}",
        )

    if mode == "static" and needs_dynamic_interaction:
        raise HTTPException(
            status_code=400,
            detail="form interactions require auto or dynamic mode",
        )

    try:
        selected_user_agent = choose_user_agent()
        selected_proxy = select_proxy(req.proxy)

        if mode == "dynamic":
            status, html, used_mode = await fetch_dynamic(
                url,
                req.auto_expand,
                input_values,
                click_selectors,
                wait_for_selector,
                wait_after_actions,
                selected_user_agent,
                selected_proxy,
            )
        else:
            status, html, used_mode = await fetch_static(
                url,
                selected_user_agent,
                selected_proxy,
            )

            if mode == "auto" and (
                should_use_dynamic(html) or needs_dynamic_interaction
            ):
                status, html, used_mode = await fetch_dynamic(
                    url,
                    req.auto_expand,
                    input_values,
                    click_selectors,
                    wait_for_selector,
                    wait_after_actions,
                    selected_user_agent,
                    selected_proxy,
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
            "proxy_enabled": selected_proxy is not None,
            "markdown": markdown,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
