import argparse
import hashlib
import html
import json
import re
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_START_URL = "https://sustech.online/"
DEFAULT_MAX_PAGES = 250
DEFAULT_MAX_DEPTH = 3
REQUEST_TIMEOUT = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl sustech.online and save PDFs + page text")
    parser.add_argument("--start-url", default=DEFAULT_START_URL, help="Seed URL for crawling")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Max HTML pages to fetch")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help="Max BFS crawl depth")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing saved files",
    )
    return parser.parse_args()


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
    )
    return session


def normalize_url(base_url: str, href: str) -> str | None:
    if not href:
        return None

    href = href.strip()
    if href.startswith("#"):
        return None
    if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
        return None

    full = urljoin(base_url, href)
    parsed = urlparse(full)
    if parsed.scheme not in {"http", "https"}:
        return None

    return full.split("#", 1)[0]


def is_same_site(url: str, root_host: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    root = root_host.lower()
    return host == root or host.endswith("." + root)


def sanitize_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or fallback


def hash_url(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def extract_links(html: str, base_url: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    links: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        full = normalize_url(base_url, href)
        if not full or full in seen:
            continue
        seen.add(full)
        links.append(full)
    return links


class _ReadableTextExtractor(HTMLParser):
    """Extract readable page text while skipping layout and navigation noise."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_tags = {
            "script",
            "style",
            "noscript",
            "svg",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "button",
            "input",
        }
        self._block_tags = {
            "article",
            "section",
            "div",
            "p",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "br",
            "main",
        }
        self._noise_attr_re = re.compile(
            r"(nav|menu|sidebar|toc|breadcrumb|footer|header|search|comment|toolbar|catalog|pagination)",
            re.IGNORECASE,
        )
        self._content_attr_re = re.compile(
            r"(content|article|main|markdown|post|page|doc)",
            re.IGNORECASE,
        )
        self._skip_depth = 0
        self._content_depth = 0
        self._saw_content_area = False
        self._skip_stack: list[bool] = []
        self._content_stack: list[bool] = []
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.lower()
        attrs_map = {str(k).lower(): str(v or "") for k, v in attrs}
        attr_blob = " ".join(
            [attrs_map.get("id", ""), attrs_map.get("class", ""), attrs_map.get("role", "")]
        )

        is_content_container = lowered in {"main", "article"} or bool(self._content_attr_re.search(attr_blob))
        is_noise_container = bool(self._noise_attr_re.search(attr_blob)) and not is_content_container
        skip_here = lowered in self._skip_tags or is_noise_container

        self._skip_stack.append(skip_here)
        self._content_stack.append(is_content_container)

        if skip_here:
            self._skip_depth += 1
        if is_content_container:
            self._content_depth += 1
            self._saw_content_area = True

        if lowered in self._block_tags and self._chunks and self._chunks[-1] != "\n":
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()

        if self._skip_stack:
            did_skip = self._skip_stack.pop()
            if did_skip and self._skip_depth > 0:
                self._skip_depth -= 1

        if self._content_stack:
            was_content = self._content_stack.pop()
            if was_content and self._content_depth > 0:
                self._content_depth -= 1

        if lowered in self._block_tags and self._chunks and self._chunks[-1] != "\n":
            self._chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag.lower() == "br":
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._saw_content_area and self._content_depth == 0:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        text = "".join(self._chunks)
        text = html.unescape(text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]

        deduped: list[str] = []
        seen_short: set[str] = set()
        for line in lines:
            if not line:
                continue
            key = line.lower()
            if len(line) <= 18:
                if key in seen_short:
                    continue
                seen_short.add(key)
            deduped.append(line)

        return "\n".join(deduped)


def html_to_text(html: str) -> str:
    main_matches = list(re.finditer(r"<main\b[\s\S]*?</main>", html, flags=re.IGNORECASE))
    html_for_parse = html
    if main_matches:
        # Prefer the largest <main> block as the best candidate content area.
        html_for_parse = max(main_matches, key=lambda m: m.end() - m.start()).group(0)

    parser = _ReadableTextExtractor()
    parser.feed(html_for_parse)
    parser.close()
    text = parser.get_text()

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if re.search(r"\b(dataLayer|gtag|vuepress-color-scheme|matchMedia)\b", candidate, flags=re.IGNORECASE):
            continue
        cleaned_lines.append(candidate)

    return "\n".join(cleaned_lines)


def infer_file_name(url: str, content_type: str, suffix: str) -> str:
    parsed = urlparse(url)
    raw_name = Path(unquote(parsed.path)).name
    raw_name = sanitize_filename(raw_name, fallback=f"file_{hash_url(url)}{suffix}")
    lower = raw_name.lower()
    if content_type.startswith("application/pdf") and not lower.endswith(".pdf"):
        return raw_name + ".pdf"
    if not lower.endswith(suffix):
        return raw_name + suffix
    return raw_name


def save_pdf(
    session: requests.Session,
    url: str,
    pdf_dir: Path,
    *,
    overwrite: bool = False,
) -> Path | None:
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        print(f"PDF下载失败: {url} ({exc})")
        return None

    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "pdf" not in content_type and not url.lower().endswith(".pdf"):
        return None

    filename = infer_file_name(url, content_type, ".pdf")
    path = pdf_dir / filename
    if path.exists() and not overwrite:
        return path

    path.write_bytes(resp.content)
    return path


def save_page_text(
    url: str,
    html: str,
    pages_dir: Path,
    *,
    overwrite: bool = False,
) -> Path | None:
    text = html_to_text(html)
    if len(text) < 60:
        return None

    parsed = urlparse(url)
    slug = sanitize_filename(Path(parsed.path).stem or "index", fallback="index")
    filename = f"{slug}_{hash_url(url)}.txt"
    path = pages_dir / filename
    if path.exists() and not overwrite:
        return path

    payload = f"URL: {url}\n\n{text}\n"
    path.write_text(payload, encoding="utf-8")
    return path

def crawl_site(start_url: str, max_pages: int, max_depth: int, *, overwrite: bool = False) -> dict[str, int]:
    root_host = urlparse(start_url).netloc
    if not root_host:
        raise ValueError(f"Invalid start URL: {start_url}")

    site_dir = OUTPUT_DIR / "sustech.online"
    pdf_dir = site_dir / "pdf"
    pages_dir = site_dir / "pages"
    site_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    session = create_session()
    queue: deque[tuple[str, int]] = deque([(start_url, 0)])
    visited: set[str] = set()
    seen_pdfs: set[str] = set()

    html_count = 0
    pdf_count = 0
    saved_pages = 0
    skipped_external = 0
    errors = 0

    print(f"Start crawl: {start_url}")
    print(f"Output: {site_dir}")
    print(f"Limits: max_pages={max_pages}, max_depth={max_depth}")

    while queue and html_count < max_pages:
        current, depth = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        if not is_same_site(current, root_host):
            skipped_external += 1
            continue

        try:
            resp = session.get(current, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            errors += 1
            print(f"请求失败: {current} ({exc})")
            continue

        content_type = (resp.headers.get("Content-Type") or "").lower()

        if "pdf" in content_type or current.lower().endswith(".pdf"):
            if current not in seen_pdfs:
                saved = save_pdf(session, current, pdf_dir, overwrite=overwrite)

                if saved is not None:
                    pdf_count += 1
                    seen_pdfs.add(current)
                    print(f"PDF保存: {saved.name}")
            continue

        if "text/html" not in content_type:
            continue

        html_count += 1
        html = resp.text

        page_path = save_page_text(current, html, pages_dir, overwrite=overwrite)
        if page_path is not None:
            saved_pages += 1
            print(f"页面保存: {page_path.name}")

        links = extract_links(html, current)
        for link in links:
            if link.lower().endswith(".pdf"):
                if link not in seen_pdfs and is_same_site(link, root_host):
                    saved = save_pdf(session, link, pdf_dir, overwrite=overwrite)
                    if saved is not None:
                        pdf_count += 1
                        seen_pdfs.add(link)
                        print(f"PDF保存: {saved.name}")
                continue

            if depth + 1 <= max_depth and link not in visited and is_same_site(link, root_host):
                queue.append((link, depth + 1))

    manifest = {
        "start_url": start_url,
        "root_host": root_host,
        "max_pages": max_pages,
        "max_depth": max_depth,
        "visited_urls": len(visited),
        "html_pages_fetched": html_count,
        "pages_saved": saved_pages,
        "pdf_saved": pdf_count,
        "external_skipped": skipped_external,
        "errors": errors,
    }
    (site_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return manifest


def main() -> None:
    args = parse_args()
    print(f"输出目录: {OUTPUT_DIR.resolve()}")
    summary = crawl_site(
        start_url=args.start_url,
        max_pages=max(args.max_pages, 1),
        max_depth=max(args.max_depth, 0),
        overwrite=args.overwrite,
    )
    print("\n抓取完成")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()