#!/usr/bin/env python3
"""Render docs/concept/README.md to an A4 PDF and report its page count.

Issue #1 limits the concept to two pages. This script renders the Markdown,
the Mermaid diagrams, and the images in headless Chromium, the way a reader
would print it, and fails if the result is longer than the limit.

Usage:
    pip install markdown playwright && playwright install chromium
    python experiments/render_concept_pdf.py [--out concept.pdf] [--png-dir DIR]

``--png-dir`` also saves a full-page PNG of the rendered document, which is
useful for pull request previews.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CONCEPT = ROOT / "docs" / "concept" / "README.md"
MAX_PAGES = 2
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

# Ordinary business-document print settings: A4, 12 mm margins, 9.5 pt text.
CSS = """
@page { size: A4; margin: 12mm; }
body { font-family: Arial, sans-serif; font-size: 9.5pt; line-height: 1.3; }
h1 { font-size: 14pt; margin: 0 0 4pt; }
h2 { font-size: 12pt; margin: 8pt 0 3pt; }
h3 { font-size: 10.5pt; margin: 6pt 0 2pt; }
p, ul, ol { margin: 2pt 0; }
li { margin: 0; }
table { border-collapse: collapse; font-size: 8.5pt; }
td, th { border: 1px solid #999; padding: 1pt 3pt; vertical-align: top; }
img { max-height: 45mm; max-width: 100%; display: block; margin: 2pt auto; }
.mermaid { text-align: center; margin: 2pt 0; }
.mermaid svg { max-height: 38mm; max-width: 100%; }
"""


def to_html(source: str) -> str:
    """Convert the concept Markdown to a printable HTML page."""
    body = markdown.markdown(source, extensions=["fenced_code", "tables"])
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        r'<div class="mermaid">\1</div>',
        body,
        flags=re.DOTALL,
    )
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        f"<base href='{CONCEPT.parent.as_uri()}/'><style>{CSS}</style>"
        f"<script src='{MERMAID_JS}'></script></head><body>{body}"
        "<script>mermaid.initialize({startOnLoad: false});"
        "mermaid.run().then(() => { document.body.dataset.ready = '1'; });"
        "</script></body></html>"
    )


def count_pages(pdf: bytes) -> int:
    """Count page objects in a PDF produced by Chromium."""
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


def main() -> int:
    """Render the concept and check the page limit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="where to save the PDF")
    parser.add_argument("--png-dir", type=Path, help="save a full-page PNG here")
    args = parser.parse_args()

    html = to_html(CONCEPT.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "concept.html"
        page_file.write_text(html, encoding="utf-8")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 794, "height": 1123})
            page.goto(page_file.as_uri())
            page.wait_for_selector("body[data-ready='1']", timeout=30_000)
            pdf = page.pdf(format="A4", print_background=True)
            if args.png_dir:
                args.png_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=args.png_dir / "concept-render.png", full_page=True
                )
            browser.close()

    if args.out:
        args.out.write_bytes(pdf)
    pages = count_pages(pdf)
    print(f"{CONCEPT.relative_to(ROOT)}: {pages} A4 page(s), limit {MAX_PAGES}")
    return 0 if pages <= MAX_PAGES else 1


if __name__ == "__main__":
    sys.exit(main())
