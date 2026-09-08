from __future__ import annotations

from urllib.parse import urljoin

from lxml import html as lhtml
import html2text

from watch_sieve.models import Topic

_DROP_TAGS = {"script", "style", "noscript", "template", "iframe", "svg", "link", "meta"}
_CHROME_TAGS = {"header", "footer", "nav", "aside"}


def extract_title(raw_html: str) -> str:
    if not raw_html:
        return ""
    try:
        tree = lhtml.fromstring(raw_html)
    except Exception:
        return ""
    titles = tree.xpath("//title/text()")
    return " ".join(titles[0].split()) if titles else ""


def to_markdown(raw_html: str, *, css_selector: str | None = None, main_content: bool = True) -> str:
    cleaned = _clean_html(raw_html, css_selector=css_selector, main_content=main_content)
    if not cleaned:
        return ""
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_images = True
    converter.ignore_emphasis = False
    converter.bypass_tables = False
    return converter.handle(cleaned).strip()


def to_text(markdown: str) -> str:
    return " ".join((markdown or "").split())


def list_titles(raw_html: str, css_selector: str, base_url: str = "") -> list[str]:
    return [topic.title for topic in list_topics(raw_html, css_selector, base_url)]


def list_topics(raw_html: str, css_selector: str, base_url: str = "") -> list[Topic]:
    if not raw_html or not css_selector:
        return []
    try:
        tree = lhtml.fromstring(raw_html)
    except Exception:
        return []
    topics: list[Topic] = []
    seen: set[str] = set()
    for node in tree.cssselect(css_selector):
        text = " ".join(node.text_content().split())
        if not text or text in seen:
            continue
        seen.add(text)
        href = _href(node)
        topics.append(Topic(title=text, url=urljoin(base_url, href) if href else ""))
    return topics


def _href(node) -> str:
    href = node.get("href") if node.tag == "a" else None
    if href:
        return href
    nested = node.xpath(".//a[@href][1]/@href")
    if nested:
        return str(nested[0])
    parent = node.getparent()
    if parent is not None and parent.tag == "a":
        return parent.get("href") or ""
    return ""


def _clean_html(raw_html: str, *, css_selector: str | None, main_content: bool) -> str:
    if not raw_html:
        return ""
    try:
        tree = lhtml.fromstring(raw_html)
    except Exception:
        return raw_html

    for tag in list(tree.iter()):
        name = (tag.tag or "").lower() if isinstance(tag.tag, str) else ""
        if name in _DROP_TAGS or (main_content and name in _CHROME_TAGS):
            parent = tag.getparent()
            if parent is not None:
                parent.remove(tag)

    if css_selector:
        matches = tree.cssselect(css_selector)
        if not matches:
            return ""
        return "\n".join(lhtml.tostring(node, encoding="unicode", method="html") for node in matches)

    body = tree.find("body")
    target = body if body is not None else tree
    return lhtml.tostring(target, encoding="unicode", method="html")
