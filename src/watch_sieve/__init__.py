"""Watch specified sites and stably fetch page content."""

from watch_sieve.crawler import WatchCrawler
from watch_sieve.models import FetchResult, SiteConfig

__version__ = "0.1.0"
__all__ = ["WatchCrawler", "FetchResult", "SiteConfig", "__version__"]
