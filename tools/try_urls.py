"""Fetch + parse real article URLs and print a one-line verdict per URL (writes UTF-8 to a file).

    python -X utf8 tools/try_urls.py out.txt URL [URL ...]
Honors robots.txt, 2 s spacing per host, honest UA. Shows what was extracted -- it does NOT
claim completeness; compare against the real page yourself.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.errors import ToolError  # noqa: E402
from src.parsers.extract import parse  # noqa: E402
from src.parsers.fetch import fetch  # noqa: E402


def main(out_path, urls):
    lines = []
    for u in urls:
        try:
            f = fetch(u)
            r = parse(f.html, f.final_url, f.warnings)
            body = r.body.value or ""
            lines.append(
                f"{r.status.upper():8} body={r.body_status:15} class={r.page_class:9} chars={len(body):6} "
                f"charset={f.charset}\n   URL   {u}\n   TITLE {r.title.value}\n   SITE  {r.site.value}"
                f"\n   AUTH  {r.author.value} [{r.author.status}/{r.author.source}]\n   TIME  {r.published.value}"
                f"\n   HEAD  {body[:70]!r}\n   TAIL  {body[-70:]!r}\n   WARN  {r.warnings}")
        except ToolError as e:
            lines.append(f"ERROR    {u}\n   {e}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print("wrote", out_path, len(lines), "entries")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
