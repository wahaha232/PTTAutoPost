"""Article extraction: generic strategies + per-site profiles, merged field by field.

Nothing is invented: a field that no strategy can supply stays MISSING. Fields that were
derived from the text (reporter byline) are INFERRED. The body gets an explicit
completeness verdict -- a found title never means "the article was fully captured".
No scripts are executed; pages are parsed as inert text.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

FOUND, MISSING, INFERRED = "found", "missing", "inferred"
TIME_NOTES: list[str] = []
ARTICLE_TYPES = {"newsarticle", "article", "blogposting", "reportagenewsarticle", "analysisnewsarticle", "opinionnewsarticle"}
ORG_WORDS = re.compile(r"(新聞|電子報|通訊社|雜誌|日報|時報|報導者|編輯部|記者群|網站|網$|Marketing|News|Media|http)", re.I)
_NOISE_TOK = ("comment|comments|related|recommend|recommended|share|sharing|social|advert|advertisement|sponsor|breadcrumb|breadcrumbs|"
              "sidebar|newsletter|subscribe|subscription|promo|widget|more-news|morenews|extended|keyword|keywords|toolbar|author-box|"
              "authorbox|author-card|author-info|author-bio|copyright|banner|popup|modal|login|paywall|adcolumn|ad|ads|ad-blk|hr-separator|tags")
NOISE_ATTR = re.compile(r"(?:^|[\s_.\-])(?:" + _NOISE_TOK + r")(?:$|[\s_.\-])", re.I)
NOISE_CAMEL = re.compile(r"__(?:Related|Recommend|Share|Social|Comment|Ad|Advert|Banner|Sponsor|Newsletter|Sidebar|Breadcrumb)\w*")
PLACES = ("台北|臺北|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|苗栗|彰化|南投|雲林|嘉義|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|連江|馬祖|"
          "華盛頓|紐約|倫敦|東京|北京|巴黎|柏林|首爾|曼谷|新加坡|雅加達|馬尼拉|布魯塞爾|莫斯科|開羅|墨爾本|雪梨|洛杉磯|舊金山")
GENERIC_AUTHOR = re.compile(r"^(作者|記者|編輯|作者群|特派員|撰文|報導|攝影|本報|網編|綜合報導)$|作者群|更多|訂閱|贊助|登入|關於|加入|追蹤")
HOST_NAMES = {
    "cna.com.tw": "中央社", "ltn.com.tw": "自由時報", "udn.com": "聯合新聞網", "ettoday.net": "ETtoday新聞雲", "chinatimes.com": "中時新聞網",
    "tvbs.com.tw": "TVBS新聞網", "setn.com": "三立新聞網", "pts.org.tw": "公視新聞網", "storm.mg": "風傳媒", "nownews.com": "NOWnews今日新聞",
    "bbc.com": "BBC News 中文", "bbc.co.uk": "BBC News 中文", "twreporter.org": "報導者", "thenewslens.com": "關鍵評論網",
    "ithome.com.tw": "iThome", "technews.tw": "科技新報", "bnext.com.tw": "數位時代", "cw.com.tw": "天下雜誌",
    "yahoo.com": "Yahoo奇摩新聞", "ptt.cc": "PTT", "wikipedia.org": "維基百科", "mirrormedia.mg": "鏡週刊", "ftvnews.com.tw": "民視新聞網",
    "ctee.com.tw": "工商時報", "money.udn.com": "經濟日報", "cnyes.com": "鉅亨網", "technice.com.tw": "科技島", "inside.com.tw": "INSIDE",
}
NOISE_PARA = re.compile(r"^(延伸閱讀|相關新聞|相關報導|更多.{0,6}報導|更多文章|責任編輯|編輯[:：]|圖／|圖片來源|照片來源|▲|▼|【.{0,12}(看更多|推薦|掌握)|"
                        r"加入.{0,10}(好友|粉絲|頻道)|訂閱|點我|按讚|喜歡這篇|\(?Photo|Copyright|版權所有|※\s*發信站|"
                        r"\d+:\d+\s*/\s*\d+:\d+|字級設定|跳過此內容|支持中央社|下載.{0,14}APP|不用抽|我是廣告|udn討論區|"
                        r"Article Information|BBC News,|加入Google|阿立幫你|新聞專題|請同意我們的隱私權|請點選打勾|首選來源|[（(]相關報導|以行動力挺|#\s*\S|熱門.{0,4}(新聞|文章)|最多人閱讀|你可能也?喜歡|推薦閱讀|Related|Advertisement)", re.I)
DATE_ONLY = re.compile(r"^\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?(\s*\d{1,2}:\d{2}(:\d{2})?)?(\s*[（(].{0,12}更新[）)])?$|^\d{1,3}$")
REL_TIME = re.compile(r"^\d+\s*(秒|分鐘|小時|天)前$")
SENT_END = re.compile(r"[。！？!?」』”\)）…\.]$")
TRUNC_MARK = re.compile(r"(展開全文|繼續閱讀|閱讀更多|閱讀全文|請登入|登入後.{0,6}閱讀|訂閱後.{0,6}閱讀|會員專屬|付費|下一頁|next page)", re.I)
BYLINES = [
    re.compile(r"[（(]\s*[^）)\s]{0,10}記者\s*([一-鿿·]{2,4}?)(?=(?:" + PLACES + r")?\s*\d{1,2}日電|[／/、，,\s）)]|攝|綜合|報導|" + PLACES + r")"),
    re.compile(r"(?:作者|撰文|文|記者|編譯|撰稿)\s*[／/｜|:：]\s*([一-鿿·A-Za-z]{1,12}(?:\s[A-Za-z]+){0,2}|[一-鿿]\s?[一-鿿]{1,3})(?=\s*[|｜／/\n(（,，]|\s*$)"),
    re.compile(r"作者\s*([一-鿿](?:\s?[一-鿿]){1,3})\s*[|｜\n]"),
    re.compile(r"([一-鿿]{2,4})\s*[｜|]\s*[^\n]{0,14}(?:記者|特派員|編輯|主播)"),
    re.compile(r"[〔\[【]\s*(?:記者|實習記者|特派記者)\s*([一-鿿]{2,4})\s*[／/]"),
    re.compile(r"[（(]\s*(?:記者|攝影記者)\s*([一-鿿]{2,4})\s*攝\s*[）)]"),
    re.compile(r"^(?:文|撰文|記者|作者|編譯|撰稿)\s*[／/:：]\s*([一-鿿A-Za-z·\s]{2,12})$", re.M),
    re.compile(r"^(?:中央社)?記者\s*([一-鿿]{2,4})\s*[／/，,]"),
    re.compile(r"([一-鿿]{2,4})\s*[／/]\s*[一-鿿]{2,6}\s*(?:報導|綜合報導|編譯)"),
]


@dataclass
class Field_:
    value: str | None = None
    status: str = MISSING
    source: str = ""

    def set(self, value, status, source):
        if value and not self.value:
            self.value, self.status, self.source = value.strip(), status, source


@dataclass
class ParseResult:
    title: Field_ = field(default_factory=Field_)
    site: Field_ = field(default_factory=Field_)
    url: Field_ = field(default_factory=Field_)
    author: Field_ = field(default_factory=Field_)
    published: Field_ = field(default_factory=Field_)
    body: Field_ = field(default_factory=Field_)
    status: str = "failed"            # success / partial / failed
    body_status: str = "insufficient"  # likely_complete / suspect_partial / insufficient
    page_class: str = "article"       # article / csr_shell / login_wall / paywall
    profile: str = "generic"
    warnings: list[str] = field(default_factory=list)

    def fields(self):
        return {"title": self.title, "site": self.site, "url": self.url, "author": self.author,
                "published": self.published, "body": self.body}


# ---------------------------------------------------------------------- helpers
def _clean(s: str | None) -> str:
    return re.sub(r"[ \t　]+", " ", (s or "").replace("\xa0", " ")).strip()


def _meta(doc, *names):
    for n in names:
        t = doc.find("meta", attrs={"property": n}) or doc.find("meta", attrs={"name": n})
        if t and t.get("content"):
            return _clean(t["content"])
    return None


def _norm_time(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            local = dt.astimezone()       # show in the user's local time zone
            if local.replace(tzinfo=None) > datetime.now() + timedelta(minutes=10):
                dt = dt.replace(tzinfo=None)    # would be in the future: the site mislabelled local time as UTC
                TIME_NOTES.append("發布時間的時區標示可能有誤（換算後會落在未來），已改用頁面上的原始時間。")
            else:
                dt = local
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?[ T]*(\d{1,2})?[:：時]?(\d{2})?", raw)
    if m:
        y, mo, d, h, mi = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}" + (f" {int(h):02d}:{int(mi or 0):02d}" if h else "")
    return raw


def _author_ok(name: str | None, site: str | None) -> bool:
    if not name:
        return False
    n = _clean(name)
    if not (2 <= len(n) <= 40) or ORG_WORDS.search(n) or GENERIC_AUTHOR.search(n):
        return False
    if site and (n in site or site in n):
        return False
    return bool(re.search(r"[一-鿿A-Za-z]", n))


_LABEL = re.compile(r"^[（(〔\[【]?\s*(?:編譯|撰文|撰稿|作者|文|記者|實習記者|特派記者|特派員|攝影|綜合報導|報導)\s*[／/｜|:：]?\s*")


def _clean_author(name: str) -> str:
    """'編譯周辰陽／即時' -> '周辰陽'; '記者 林意筑 彰化報導' -> '林意筑'; '蘇 子芸' -> '蘇子芸'."""
    n = _clean(name)
    m = re.search(r"記者\s*([一-鿿·]{2,4}?)(?=(?:" + PLACES + r")|[／/、，,\s]|攝|報導|$)", n)
    if m:
        return m.group(1)
    for _ in range(3):
        n2 = _LABEL.sub("", n)
        if n2 == n:
            break
        n = n2
    n = re.split(r"[／/｜|]", n)[0]
    n = re.sub(r"\s*(綜合報導|報導|攝影|編譯|即時)$", "", n).strip("）)〕】] ")
    return re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", n).strip()


def _author_from_dom(doc, site):
    sel = "[itemprop=author], a[rel=author], [rel=author], .author, .byline, [class*=author], [class*=byline], [class*=reporter], [class*=writer]"
    for el in doc.select(sel)[:40]:
        if el.find_parent(["nav", "footer", "aside", "header"]) and not el.find_parent("article"):
            continue
        txt = _clean_author(el.get_text(" ", strip=True))
        if txt and len(txt) <= 20 and _author_ok(txt, site):
            return txt
    return None


def _author_from_text(probe: str, site):
    for rx in BYLINES:
        for m in rx.finditer(probe):
            cand = _clean_author(m.group(1))
            if _author_ok(cand, site):
                return cand
    return None


def _strip_title_suffix(title: str, site: str | None) -> str:
    parts = re.split(r"\s+[|｜\-–—]\s+|\s*[|｜]\s*", title)
    if len(parts) > 1:
        keep = [parts[0]]
        for p in parts[1:]:
            if site and (p.strip() in site or site in p.strip()):
                continue
            if re.search(r"(新聞網|電子報|新聞雲|雜誌|日報|時報|報導者|新聞|CNA|PNN|News|NOWnews|關鍵評論網)$", p.strip()):
                continue
            keep.append(p)
        return " | ".join(keep) if len(keep) > 1 else keep[0]
    return title


# ---------------------------------------------------------------------- strategies
def _jsonld(doc, warnings):
    out = {}
    nodes = []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("@type")
            ts = [t] if isinstance(t, str) else (t or [])
            if any(isinstance(x, str) and x.lower() in ARTICLE_TYPES for x in ts):
                nodes.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for s in doc.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        txt = s.string or s.get_text() or ""
        try:
            walk(json.loads(re.sub(r"[\x00-\x1f]+", " ", txt)))
        except ValueError:
            warnings.append("頁面的 JSON-LD 結構化資料損壞，已略過該來源。")
    if not nodes:
        return out
    n = nodes[0]
    out["title"] = n.get("headline") or n.get("name")
    out["published"] = n.get("datePublished")
    out["body_len"] = len(n.get("articleBody") or "")
    pub = n.get("publisher")
    if isinstance(pub, dict):
        out["site"] = pub.get("name")
    au = n.get("author")
    names = []
    for a in au if isinstance(au, list) else [au]:
        if isinstance(a, dict) and a.get("name") and (a.get("@type") in (None, "Person") or "person" in str(a.get("@type")).lower()):
            names.append(a["name"])
        elif isinstance(a, str):
            names.append(a)
    out["authors"] = names
    return out


BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
         "figure", "table", "tr", "td", "th", "pre", "header", "dl", "dt", "dd", "body", "html"}


def _paragraph_texts(root: Tag) -> list[str]:
    """Text runs separated by block boundaries and <br>; handles text that sits directly in a <div>."""
    paras: list[str] = []
    buf: list[str] = []

    def flush():
        t = _clean("".join(buf))
        if t:
            paras.append(t)
        buf.clear()

    def walk(node):
        for ch in node.children:
            if isinstance(ch, Comment):
                continue
            if isinstance(ch, NavigableString):
                buf.append(str(ch))
            elif isinstance(ch, Tag):
                if ch.name == "br":
                    flush()
                elif ch.name in BLOCK:
                    flush()
                    walk(ch)
                    flush()
                else:
                    walk(ch)

    walk(root)
    flush()
    return paras


def _link_density(el: Tag) -> float:
    total = len(el.get_text(strip=True)) or 1
    return sum(len(a.get_text(strip=True)) for a in el.find_all("a")) / total


def _strip_noise(root: Tag):
    for t in root.find_all(["script", "style", "noscript", "iframe", "form", "nav", "aside", "footer", "figcaption",
                            "button", "svg", "template", "select"]):
        t.decompose()
    total = len(root.get_text(strip=True))
    for t in list(root.find_all(True)):
        if t.attrs is None or t.name in ("article", "main", "body", "html"):
            continue
        cls = t.get("class", [])
        ident = " ".join([" ".join(cls if isinstance(cls, list) else [str(cls or "")]), str(t.get("id") or "")])
        if ident.strip() and (NOISE_ATTR.search(ident) or NOISE_CAMEL.search(ident)):
            if total > 300 and len(t.get_text(strip=True)) > 0.6 * total:
                continue                      # that block IS (most of) the page text: never throw the content away
            t.decompose()


INLINE = {"span", "a", "strong", "em", "b", "i", "u", "font", "small", "mark", "sup", "sub", "abbr", "cite", "label", "br"}


def _own_text_len(t: Tag) -> int:
    n = 0
    for ch in t.children:
        if isinstance(ch, Comment):
            continue
        if isinstance(ch, NavigableString):
            n += len(str(ch).strip())
        elif isinstance(ch, Tag) and ch.name in INLINE:
            n += len(ch.get_text(strip=True))
    return n


def _dense_parents(doc, top: int = 3):
    scores: dict[int, list] = {}
    body = doc.body
    if body is None:
        return []
    for t in body.find_all(True):
        if t.name in ("script", "style", "nav", "footer", "aside", "noscript", "head"):
            continue
        n = _own_text_len(t)
        if n < 25 or t.name in INLINE:
            continue
        for anc in (t, t.parent, t.parent.parent if t.parent is not None else None):
            if anc is not None and anc.name not in ("html", "body", "[document]"):
                scores.setdefault(id(anc), [anc, 0])[1] += n
    ranked = sorted(scores.values(), key=lambda v: -(v[1] * max(0.1, 1 - _link_density(v[0]))))
    return [v[0] for v in ranked[:top]]


def _candidates(doc, selectors):
    """Ordered candidate containers: profile selectors, itemprop, <article>, class/id hints, <body>."""
    out, seen = [], set()

    def add(el, kind):
        if el is not None and id(el) not in seen:
            seen.add(id(el))
            out.append((el, kind))

    for sel in selectors:
        try:
            add(doc.select_one(sel), "profile")
        except Exception:  # noqa: BLE001
            pass
    for el in doc.select("[itemprop=articleBody]"):
        add(el, "itemprop")
    for el in doc.find_all("article"):
        add(el, "article")
    for el in _dense_parents(doc):
        add(el, "dense")                      # blocks holding most of the page's own text (no <article>, CSS-in-JS classes)
    for el in doc.find_all(["div", "section", "main"], attrs={"class": re.compile(r"(article|content|story|post|entry|news|body|text)", re.I)})[:40]:
        add(el, "generic")
    for el in doc.find_all(["div", "section"], attrs={"id": re.compile(r"(article|content|story|post|entry|news|body|main)", re.I)})[:20]:
        add(el, "generic")
    add(doc.body, "body")
    return out


def _paragraphs_of(el):
    root_doc = BeautifulSoup(str(el), "lxml")                 # work on a copy
    root = root_doc.body or root_doc
    _strip_noise(root)
    paras, prev = [], None
    raw = _paragraph_texts(root)
    _paragraphs_of.raw_tail = " | ".join(raw[-6:])
    for p in raw:
        if len(p) < 3 or NOISE_PARA.match(p) or DATE_ONLY.match(p) or p.startswith("<") or "allowfullscreen" in p or "</" in p:
            continue
        if p != prev:
            paras.append(p)
        prev = p
    return paras, root


def _trim_tail(paras):
    """Cut related-news lists: at a relative-time stamp ("6小時前"), and runs (>=3) of trailing short non-sentence lines."""
    n0 = len(paras)
    for i, p in enumerate(paras):
        if REL_TIME.match(p) and i >= 1 and sum(len(x) for x in paras[:i - 1]) >= 120:
            del paras[i - 1:]
            break
    j = len(paras)
    while j > 0 and len(paras[j - 1]) < 45 and not re.search(r"[，。；,]", paras[j - 1]):
        j -= 1
    if len(paras) - j >= 2:
        del paras[j:]
    return n0 - len(paras)


def _trim_head(paras, title):
    """Drop leading short non-sentence lines (section labels, repeated title, widgets) before the real text."""
    n0, t = len(paras), (title or "").strip()
    while len(paras) > 2:
        p0 = paras[0]
        is_title = bool(t) and (p0 == t or (len(p0) >= 8 and p0 in t) or (len(t) >= 8 and t in p0 and len(p0) < len(t) + 12))
        looks_byline = re.search(r"記者|報導|電）|編譯|撰|／|來源|發布時間|更新時間", p0) is not None
        short_label = len(p0) < 40 and not re.search(r"[，。！？]", p0) and not looks_byline
        if (is_title or short_label) and sum(len(x) for x in paras[1:]) >= 150:
            paras.pop(0)
        else:
            break
    return n0 - len(paras)


KIND_RANK = {"profile": 0, "itemprop": 1, "article": 2, "dense": 3, "generic": 4, "body": 5}


def _extract_body(doc, selectors, warnings, hint_len=0, title=None):
    scored = []
    for el, kind in _candidates(doc, selectors)[:18]:
        paras, root = _paragraphs_of(el)
        chars = sum(len(p) for p in paras)
        if chars == 0:
            continue
        scored.append({"kind": kind, "paras": paras, "chars": chars, "score": chars * max(0.1, 1 - _link_density(el)), "root": root,
                       "raw_tail": getattr(_paragraphs_of, "raw_tail", "")})
    if not scored:
        return [], "none", None

    def order(c):
        near = hint_len >= 200 and 0.7 * hint_len <= c["chars"] <= 2.5 * hint_len
        ratio = abs(c["chars"] / hint_len - 1) if hint_len >= 200 else 0
        need = 400 if c["kind"] == "dense" else 150
        return (0 if near else 1, KIND_RANK[c["kind"]] if (near or c["chars"] >= need) else 9, ratio, -c["score"])

    best = None
    for c in sorted(scored, key=order):
        paras = list(c["paras"])
        dropped = _trim_tail(paras)
        head_dropped = _trim_head(paras, title)
        chars = sum(len(x) for x in paras)
        want = max(120, 0.5 * hint_len) if hint_len >= 200 else 120
        if best is None or chars > best[2]:
            best = (c, paras, chars, dropped + head_dropped)
        if chars >= want:
            best = (c, paras, chars, dropped + head_dropped)
            break
    c, paras, chars, dropped = best
    _extract_body.trunc = bool(TRUNC_MARK.search(c["raw_tail"]))
    if dropped:
        warnings.append(f"已自動移除 {dropped} 行疑似非內文的短行（開頭的版面標籤／重複標題，或結尾的相關新聞、標籤）；若內文被誤刪請自行補回。")
    return paras, c["kind"], c["root"]


# ---------------------------------------------------------------------- site profiles
PROFILES: dict[str, dict] = {
    # host suffix -> declarative hints. Only add an entry after a real page proved the generic path insufficient.
}


def _ptt_web(doc, res: ParseResult):
    main = doc.select_one("#main-content")
    if main is None:
        return False
    meta = {}
    for ml in main.select(".article-metaline"):
        k = ml.select_one(".article-meta-tag")
        v = ml.select_one(".article-meta-value")
        if k and v:
            meta[_clean(k.get_text())] = _clean(v.get_text())
    board = main.select_one(".article-metaline-right .article-meta-value")
    res.title.set(meta.get("標題"), FOUND, "ptt-web")
    if meta.get("作者"):
        res.author.set(re.sub(r"\s*\(.*\)$", "", meta["作者"]), FOUND, "ptt-web")
    res.published.set(_norm_time(meta.get("時間")), FOUND, "ptt-web")
    res.site.set("PTT" + (f" {board.get_text(strip=True)}板" if board else ""), FOUND, "ptt-web")
    for t in main.select(".article-metaline, .article-metaline-right, .push, .richcontent"):
        t.decompose()
    text = main.get_text("\n")
    text = re.split(r"\n--\n|\n※ 發信站", text)[0]
    lines = [ln.rstrip() for ln in text.splitlines()]
    res.body.set("\n".join(lines).strip(), FOUND, "ptt-web")
    res.profile = "ptt-web"
    return True


# ---------------------------------------------------------------------- main entry
def parse(html: str, url: str, extra_warnings: list[str] | None = None) -> ParseResult:
    res = ParseResult()
    TIME_NOTES.clear()
    res.warnings.extend(extra_warnings or [])
    doc = BeautifulSoup(html, "lxml")
    host = (urlparse(url).hostname or "").lower()
    res.url.set(url, FOUND, "request")

    visible = re.sub(r"\s+", "", BeautifulSoup(html, "lxml").get_text())
    if host.endswith("ptt.cc") and _ptt_web(doc, res):
        res.body_status = "likely_complete" if len(res.body.value or "") >= 20 else "insufficient"
        _finish(res, None)
        return res

    ld = _jsonld(doc, res.warnings)
    og_site = _meta(doc, "og:site_name", "application-name")
    res.site.set(og_site, FOUND, "og:site_name")
    res.site.set(ld.get("site"), FOUND, "json-ld")
    title_raw = ld.get("title") or _meta(doc, "og:title", "twitter:title")
    if not title_raw:
        h1 = doc.find("h1")
        title_raw = _clean(h1.get_text()) if h1 else (_clean(doc.title.string) if doc.title and doc.title.string else None)
    if title_raw:
        res.title.set(_strip_title_suffix(_clean(title_raw), res.site.value), FOUND, "json-ld/og/h1")
    canon = doc.find("link", rel="canonical")
    curl = (canon.get("href") if canon else None) or _meta(doc, "og:url")
    if curl and urlparse(curl).hostname and urlparse(curl).hostname.split(".")[-2:] == urlparse(url).hostname.split(".")[-2:]:
        res.url.value, res.url.source = curl, "canonical"
    t_el = doc.find("time", attrs={"datetime": True})
    res.published.set(_norm_time(ld.get("published") or _meta(doc, "article:published_time", "og:article:published_time", "pubdate",
                                                              "datePublished", "date")
                                 or (t_el["datetime"] if t_el else None)), FOUND, "json-ld/meta/time")
    names = [c for c in (_clean_author(n) for n in ld.get("authors", [])) if _author_ok(c, res.site.value)]
    if names:
        res.author.set("、".join(dict.fromkeys(names[:3])), FOUND, "json-ld")
    for key in ("author", "article:author", "dable:author", "parsely-author", "byl"):
        cand = _clean_author(_meta(doc, key) or "")
        if _author_ok(cand, res.site.value):
            res.author.set(cand, FOUND, "meta")
            break
    # media source fallbacks (only when og:site_name / JSON-LD had nothing)
    if not res.site.value:
        tc = _meta(doc, "twitter:creator", "publisher")
        if tc and not tc.startswith("@") and 2 <= len(tc) <= 20:
            res.site.set(tc, FOUND, "meta")
        for key, name in HOST_NAMES.items():
            if host == key or host.endswith("." + key):
                res.site.set(name, INFERRED, "host-map")
                break
        if not res.site.value and title_raw:
            parts = re.split(r"\s+[|｜\-–—]\s+|\s*[|｜]\s*", _clean(title_raw))
            if len(parts) > 1 and 2 <= len(parts[-1].strip()) <= 16:
                res.site.set(parts[-1].strip(), INFERRED, "title-suffix")
        if not res.site.value and host:
            res.site.set(host[4:] if host.startswith("www.") else host, INFERRED, "domain")
        if res.title.value and title_raw:
            res.title.value = _strip_title_suffix(_clean(title_raw), res.site.value) or res.title.value

    paras, how, container = _extract_body(doc, PROFILES.get(host, {}).get("body", []), res.warnings, ld.get("body_len") or 0, res.title.value)
    body_text = "\n\n".join(paras)
    res.body.set(body_text, FOUND, how)

    if not res.author.value:
        dom_author = _author_from_dom(doc, res.site.value)
        if dom_author:
            res.author.set(dom_author, FOUND, "dom-author")
    # reporter byline inferred from the text (never presented as "found")
    if not res.author.value:
        art = doc.find("article") or doc.find("main")
        header = re.sub(r"[ \t]+", " ", art.get_text("\n", strip=True))[:900] if art else ""
        probe = "\n".join(paras[:3] + paras[-2:]) + "\n" + header
        cand = _author_from_text(probe, res.site.value)
        if cand:
            res.author.set(cand, INFERRED, "byline-in-text")

    res.warnings.extend(dict.fromkeys(TIME_NOTES))
    _finish(res, ld, visible=visible, html=html, container=container)
    return res


def _finish(res: ParseResult, ld, visible: str = "", html: str = "", container=None):
    body = res.body.value or ""
    n = len(re.sub(r"\s", "", body))
    page_text = visible or body
    # access walls / client-side rendering: report, never bypass
    low = html.lower()
    if n < 200 and len(page_text) < 400 and ("__next_data__" in low or 'id="root"' in low or "enable javascript" in low
                                              or "請啟用 javascript" in low or "<noscript" in low):
        res.page_class = "csr_shell"
        res.warnings.append("此頁面需要執行 JavaScript 才會顯示內容（前端渲染），無法以靜態方式取得全文。請改用手動貼上內文。")
    elif n < 300 and re.search(r"(請登入|登入後|會員登入|please log ?in|sign in to (read|continue))", page_text, re.I):
        res.page_class = "login_wall"
        res.warnings.append("頁面疑似需要登入才能閱讀全文；程式不會嘗試繞過，請自行取得內文後貼上。")
    elif re.search(r"(訂閱後|付費會員|會員專屬|付費閱讀|subscribe to (read|continue))", page_text[-1500:] + body[-400:], re.I) and n < 1500:
        res.page_class = "paywall"
        res.warnings.append("頁面疑似有付費牆，內文可能只有前段；程式不會嘗試繞過。")

    # completeness verdict (never "certainly complete")
    if n < 120:
        res.body_status = "insufficient"
    else:
        res.body_status = "likely_complete"
        reasons = []
        if TRUNC_MARK.search(body[-300:]) or getattr(_extract_body, "trunc", False):
            reasons.append("內文結尾附近出現「展開全文／繼續閱讀／訂閱」等字樣")
        if container is not None and container.find("a", rel=re.compile("next")):
            reasons.append("頁面有分頁連結（rel=next）")
        if ld and ld.get("body_len") and ld["body_len"] > n * 1.3 + 100:
            reasons.append(f"結構化資料中的 articleBody（{ld['body_len']} 字）比擷取的內文（{n} 字）長得多")
        if res.page_class in ("paywall", "login_wall"):
            reasons.append("疑似存取限制")
        if reasons:
            res.body_status = "suspect_partial"
            res.warnings.append("內文可能不完整：" + "；".join(reasons) + "。請對照原網頁確認。")
    if res.body_status == "insufficient" and res.page_class == "article":
        res.warnings.append("擷取到的內文過短或沒有內文，請對照原網頁或手動貼上。")

    missing = [lbl for lbl, f in (("標題", res.title), ("媒體來源", res.site), ("作者", res.author), ("發布時間", res.published)) if not f.value]
    if missing:
        res.warnings.append("未取得：" + "、".join(missing) + "（請自行填寫；程式不會補造）。")
    if res.author.status == INFERRED:
        res.warnings.append("作者由內文署名推定，請確認是否正確。")

    if not res.title.value and not body:
        res.status = "failed"
    elif res.title.value and res.body_status == "likely_complete":
        res.status = "success"
    else:
        res.status = "partial"
