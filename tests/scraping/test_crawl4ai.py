"""Tests for Crawl4AiFetcher with mocked AsyncWebCrawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import (
    Crawl4AiFetcher,
    StealthLevel,
)


def test_stealth_level_values():
    """StealthLevel enum has expected string values."""
    assert StealthLevel.OFF == "off"
    assert StealthLevel.STEALTH == "stealth"
    assert StealthLevel.UNDETECTED == "undetected"


async def test_default_stealth_is_stealth():
    """Crawl4AiFetcher defaults to STEALTH level."""
    fetcher = Crawl4AiFetcher()
    assert fetcher._stealth == StealthLevel.STEALTH


async def test_constructor_accepts_stealth_level():
    """Crawl4AiFetcher accepts explicit stealth level."""
    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)
    assert fetcher._stealth == StealthLevel.OFF

    fetcher2 = Crawl4AiFetcher(stealth=StealthLevel.UNDETECTED)
    assert fetcher2._stealth == StealthLevel.UNDETECTED


def _mock_crawl_result(html="<h1>Sale</h1>", markdown="# Sale", status_code=200):
    """Create a mock CrawlResult."""
    result = MagicMock()
    result.html = html
    result.markdown = markdown
    result.status_code = status_code
    result.success = status_code == 200
    return result


async def test_fetch_success():
    """Successful fetch returns HTML and markdown from crawler."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result()

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.fetcher == "crawl4ai"
    assert result.html == "<h1>Sale</h1>"
    assert result.markdown == "# Sale"


async def test_fetch_passes_url_to_crawler():
    """The URL is forwarded to the crawler."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result()

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    await fetcher.fetch("https://county.gov/auction")

    mock_crawler.arun.assert_called_once()
    call_args = mock_crawler.arun.call_args
    assert call_args[0][0] == "https://county.gov/auction" or call_args.kwargs.get("url") == "https://county.gov/auction"


async def test_fetch_error_propagates():
    """Crawler errors propagate as exceptions."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = RuntimeError("Browser crashed")

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(RuntimeError, match="Browser crashed"):
        await fetcher.fetch("https://example.com")


async def test_fetch_4xx_raises_permanent_error():
    """4xx status from crawled page raises PermanentFetchError."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result(status_code=403)

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(PermanentFetchError) as exc_info:
        await fetcher.fetch("https://example.com")

    assert exc_info.value.status_code == 403


async def test_fetch_5xx_raises_runtime_error():
    """5xx status from crawled page raises RuntimeError (retryable)."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result(status_code=500)

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(RuntimeError, match="server error 500"):
        await fetcher.fetch("https://example.com")


@pytest.fixture
def mock_crawler():
    """Provide a mock AsyncWebCrawler with a default successful result."""
    crawler = AsyncMock()
    crawler.arun.return_value = _mock_crawl_result()
    return crawler


async def test_fetch_passes_js_code_and_wait_for(mock_crawler):
    """Crawl4AI fetcher should pass js_code and wait_for to arun()."""
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    js = "document.querySelector('#search').click();"
    wait = "#results"

    await fetcher.fetch("https://example.com", js_code=js, wait_for=wait)

    mock_crawler.arun.assert_called_once()
    call_kwargs = mock_crawler.arun.call_args
    assert call_kwargs[0][0] == "https://example.com"
    assert call_kwargs[1].get("js_code") == js
    assert call_kwargs[1].get("wait_for") == wait


async def test_fetch_omits_js_code_when_none(mock_crawler):
    """When js_code/wait_for are None, don't pass them to arun()."""
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)

    await fetcher.fetch("https://example.com")

    call_kwargs = mock_crawler.arun.call_args
    assert "js_code" not in call_kwargs[1]
    assert "wait_for" not in call_kwargs[1]


# --- Gap-fill tests: _get_crawler() lazy init ---


async def test_get_crawler_import_error():
    """Missing crawl4ai package raises RuntimeError."""
    fetcher = Crawl4AiFetcher()  # no crawler injected

    with patch.dict("sys.modules", {"crawl4ai": None, "crawl4ai.async_configs": None}):
        with pytest.raises(RuntimeError, match="crawl4ai is required"):
            await fetcher.fetch("https://example.com")


async def test_get_crawler_browser_init_failure():
    """Failed browser init raises RuntimeError with setup hint."""
    mock_module = MagicMock()
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(side_effect=OSError("no browser"))
    mock_module.AsyncWebCrawler.return_value = mock_crawler_instance

    mock_configs = MagicMock()

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)

    with patch.dict("sys.modules", {"crawl4ai": mock_module, "crawl4ai.async_configs": mock_configs}):
        with pytest.raises(RuntimeError, match="Failed to initialize headless browser"):
            await fetcher.fetch("https://example.com")


async def test_get_crawler_lazy_creates_once():
    """Lazy init creates crawler on first call, reuses on second."""
    mock_module = MagicMock()
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_module.AsyncWebCrawler.return_value = mock_crawler_instance

    mock_configs = MagicMock()

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)

    with patch.dict("sys.modules", {"crawl4ai": mock_module, "crawl4ai.async_configs": mock_configs}):
        await fetcher.fetch("https://example.com")
        await fetcher.fetch("https://example.com/page2")

    # AsyncWebCrawler() called only once
    assert mock_module.AsyncWebCrawler.call_count == 1


# --- Tests: _get_crawler() stealth level configuration ---


async def test_get_crawler_stealth_configures_browser():
    """STEALTH level passes BrowserConfig(headless=True, enable_stealth=True) to AsyncWebCrawler."""
    mock_browser_config = MagicMock()
    mock_browser_config_cls = MagicMock(return_value=mock_browser_config)

    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.BrowserConfig = mock_browser_config_cls
    mock_configs.CrawlerRunConfig = MagicMock()

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.STEALTH)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
    }):
        await fetcher.fetch("https://example.com")

    mock_browser_config_cls.assert_called_once_with(headless=True, enable_stealth=True)
    mock_web_crawler_cls.assert_called_once_with(config=mock_browser_config)


async def test_get_crawler_off_uses_plain_crawler():
    """OFF level creates AsyncWebCrawler with no config."""
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.CrawlerRunConfig = MagicMock()

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
    }):
        await fetcher.fetch("https://example.com")

    mock_web_crawler_cls.assert_called_once_with()


# --- Gap-fill tests: generic exception wrapping ---


async def test_fetch_wraps_generic_exception():
    """Non-OSError/RuntimeError exceptions are wrapped in RuntimeError."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = ValueError("unexpected")

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    with pytest.raises(RuntimeError, match="Crawl4AI failed for"):
        await fetcher.fetch("https://example.com")


# --- Gap-fill tests: missing status_code ---


async def test_fetch_missing_status_code_defaults_to_200():
    """Result without status_code attribute defaults to 200."""
    mock_crawler = AsyncMock()
    result = MagicMock(spec=[])  # empty spec = no attributes
    result.html = "<h1>Sale</h1>"
    result.markdown = "# Sale"
    # no status_code attribute at all
    mock_crawler.arun.return_value = result

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    fetch_result = await fetcher.fetch("https://example.com")

    assert fetch_result.status_code == 200


async def test_fetch_none_status_code_defaults_to_200():
    """Result with status_code=None defaults to 200."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = _mock_crawl_result(status_code=None)

    fetcher = Crawl4AiFetcher(crawler=mock_crawler)
    fetch_result = await fetcher.fetch("https://example.com")

    assert fetch_result.status_code == 200


# --- Gap-fill tests: close() ---


async def test_close_owned_crawler():
    """close() calls __aexit__ on crawler we own."""
    mock_module = MagicMock()
    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.__aexit__ = AsyncMock()
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_module.AsyncWebCrawler.return_value = mock_crawler_instance

    mock_configs = MagicMock()

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.OFF)

    with patch.dict("sys.modules", {"crawl4ai": mock_module, "crawl4ai.async_configs": mock_configs}):
        await fetcher.fetch("https://example.com")

    await fetcher.close()
    mock_crawler_instance.__aexit__.assert_called_once()
    assert fetcher._crawler is None


async def test_close_injected_crawler_is_noop():
    """close() does not close an injected crawler."""
    mock_crawler = AsyncMock()
    fetcher = Crawl4AiFetcher(crawler=mock_crawler)

    await fetcher.close()
    mock_crawler.__aexit__.assert_not_called()


async def test_close_without_init_is_noop():
    """close() before any fetch is a safe no-op."""
    fetcher = Crawl4AiFetcher()
    await fetcher.close()  # should not raise


# --- Tests: UNDETECTED level ---


async def test_get_crawler_undetected_uses_adapter_and_strategy():
    """UNDETECTED level uses UndetectedAdapter + AsyncPlaywrightCrawlerStrategy."""
    mock_browser_config = MagicMock()
    mock_browser_config_cls = MagicMock(return_value=mock_browser_config)

    mock_adapter = MagicMock()
    mock_adapter_cls = MagicMock(return_value=mock_adapter)

    mock_strategy = MagicMock()
    mock_strategy_cls = MagicMock(return_value=mock_strategy)

    mock_crawler_instance = MagicMock()
    mock_crawler_instance.__aenter__ = AsyncMock(return_value=mock_crawler_instance)
    mock_crawler_instance.arun = AsyncMock(return_value=_mock_crawl_result())
    mock_web_crawler_cls = MagicMock(return_value=mock_crawler_instance)

    mock_configs = MagicMock()
    mock_configs.BrowserConfig = mock_browser_config_cls
    mock_configs.CrawlerRunConfig = MagicMock()

    mock_crawl4ai = MagicMock()
    mock_crawl4ai.AsyncWebCrawler = mock_web_crawler_cls
    mock_crawl4ai.UndetectedAdapter = mock_adapter_cls

    mock_strategy_module = MagicMock()
    mock_strategy_module.AsyncPlaywrightCrawlerStrategy = mock_strategy_cls

    fetcher = Crawl4AiFetcher(stealth=StealthLevel.UNDETECTED)

    with patch.dict("sys.modules", {
        "crawl4ai": mock_crawl4ai,
        "crawl4ai.async_configs": mock_configs,
        "crawl4ai.async_crawler_strategy": mock_strategy_module,
    }):
        await fetcher.fetch("https://example.com")

    mock_browser_config_cls.assert_called_once_with(headless=True, enable_stealth=True)
    mock_adapter_cls.assert_called_once_with()
    mock_strategy_cls.assert_called_once_with(
        browser_config=mock_browser_config,
        browser_adapter=mock_adapter,
    )
    mock_web_crawler_cls.assert_called_once_with(crawler_strategy=mock_strategy)
