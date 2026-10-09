"""Read web pages on this machine.

`web_extract` needs a reader: something that fetches a page and hands back its text.
Hermes's readers are services (Firecrawl, Tavily, Exa, Parallel), so every page a
companion opened went to one of them first -- or, with none configured, to whichever
anonymous free tier Hermes picked. This reader fetches the page straight from its own
site and turns it into text here, so nothing else learns what she reads.

Standard library only, apart from the HTTP client Hermes already ships, so it runs
wherever Hermes does. Hermes keeps every control it applies to any reader: URLs that
carry secrets are refused, private addresses are blocked before the fetch and again
at connect time (redirects included, since the client comes from Hermes's SSRF-safe
factory), website policy applies, and results are cached and trimmed by Hermes.

Installed into each profile as the `tamanitomo-reader` plugin by companion_routing.
"""

from __future__ import annotations

import asyncio
import json
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

NAME = "tamanitomo-reader"
MAX_BYTES = 6 * 1024 * 1024
# Parsing is pure Python; a page past this is almost always markup, not prose.
MAX_HTML_CHARS = 3_000_000
MAX_CONTENT_CHARS = 400_000
TIMEOUT = 25.0
MAX_REDIRECTS = 8
# Below this much text a page is usually built by its scripts, which only a browser runs.
THIN = 200
MAX_DEPTH = 120
MAX_FEED_ITEMS = 50
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    "Accept-Language": "en;q=0.9,*;q=0.5",
}
BROWSER_HINT = "Open it with the browser tool (browser_navigate), which runs a browser on this machine."

# fmt: off
VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
# Never content, wherever it appears.
JUNK = {
    "script", "style", "noscript", "template", "svg", "canvas", "iframe", "object",
    "embed", "button", "select", "option", "input", "textarea", "head", "dialog",
    "map", "audio", "video", "source", "track", "link", "meta", "title", "base",
}
# Site furniture: dropped when reading an article, kept in a whole-page read only
# if it is not one of the obvious landmarks.
LANDMARKS = {"nav", "aside", "footer"}
LANDMARK_ROLES = {
    "navigation", "banner", "contentinfo", "complementary", "search", "menu",
    "menubar", "alertdialog", "dialog",
}
BLOCK = {
    "address", "article", "aside", "blockquote", "body", "caption", "center", "dd",
    "details", "dir", "div", "dl", "dt", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr",
    "html", "li", "main", "menu", "nav", "ol", "p", "pre", "section", "summary",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}
# fmt: on
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
# Opening one of these closes a paragraph that is still open, as browsers do.
CLOSES_P = BLOCK - {
    "td",
    "th",
    "tr",
    "tbody",
    "thead",
    "tfoot",
    "caption",
    "body",
    "html",
}
# Class and id words that mark furniture rather than the piece itself.
UNLIKELY = re.compile(
    r"ad-break|adbox|agegate|banner|breadcrumb|combx|comment|community|consent|cookie|"
    r"disqus|footer|gdpr|header|legal|masthead|menu|newsletter|outbrain|pager|"
    r"pagination|paywall|popup|promo|related|remark|replies|rss|share|sharing|"
    r"shoutbox|sidebar|skip|skyscraper|social|sponsor|subscribe|taboola|toolbar|"
    r"tooltip|widget",
    re.I,
)
MAYBE = re.compile(r"and|article|body|column|content|main|post|story|text", re.I)
POSITIVE = re.compile(
    r"article|body|content|entry|h-entry|hentry|main|page|post|prose|recipe|story|text|blog",
    re.I,
)
NEGATIVE = re.compile(
    r"-ad-|byline|comment|contact|foot|footnote|gdpr|hidden|masthead|media|meta|nav|"
    r"outbrain|promo|related|scroll|share|sidebar|social|sponsor|shopping|tags|tool|widget",
    re.I,
)
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
SPACE = re.compile(r"[ \t\r\n\f\v  -   　]+")
CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I)


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None, text=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent
        self.text = text

    def kids(self):
        return [ch for ch in self.children if ch.tag is not None]


class Tree(HTMLParser):
    """A forgiving element tree: browsers' implied end tags for p, li, td and the
    like, and a depth cap so pathological nesting cannot exhaust the stack."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def _open(self, *tags, stop=()):
        for i in range(len(self.stack) - 1, 0, -1):
            tag = self.stack[i].tag
            if tag in tags:
                return i
            if tag in stop:
                return None
        return None

    def _close_to(self, index):
        if index is not None:
            del self.stack[index:]

    def handle_starttag(self, tag, attrs):
        if tag in CLOSES_P:
            self._close_to(self._open("p", stop=("button", "td", "th", "li", "table")))
        if tag == "li":
            self._close_to(self._open("li", stop=("ul", "ol", "menu", "dir")))
        elif tag in ("dt", "dd"):
            self._close_to(self._open("dt", "dd", stop=("dl",)))
        elif tag in ("td", "th"):
            self._close_to(self._open("td", "th", stop=("tr", "table")))
        elif tag == "tr":
            self._close_to(self._open("tr", stop=("table",)))
        elif tag in ("thead", "tbody", "tfoot"):
            self._close_to(self._open("thead", "tbody", "tfoot", stop=("table",)))
        parent = self.stack[-1]
        node = Node(tag, {k: (v or "") for k, v in attrs if k}, parent)
        parent.children.append(node)
        if tag not in VOID and len(self.stack) < MAX_DEPTH:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        parent = self.stack[-1]
        parent.children.append(Node(tag, {k: (v or "") for k, v in attrs if k}, parent))

    def handle_endtag(self, tag):
        index = self._open(tag)
        if index is not None:
            del self.stack[index:]

    def handle_data(self, data):
        parent = self.stack[-1]
        if parent.tag in ("script", "style", "template", "noscript"):
            return
        last = parent.children[-1] if parent.children else None
        if last is not None and last.tag is None:
            last.text += data
        else:
            parent.children.append(Node(None, parent=parent, text=data))


def parse(markup):
    tree = Tree()
    try:
        tree.feed(markup[:MAX_HTML_CHARS])
        tree.close()
    except (AssertionError, ValueError):  # malformed beyond repair: keep what was built
        pass
    return tree.root


def walk(node):
    """Every element below `node`, depth first, without recursion."""
    stack = list(reversed(node.kids()))
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.kids()))


def find(node, tag):
    return next((n for n in walk(node) if n.tag == tag), None)


def collapse(text):
    return SPACE.sub(" ", text)


def junk(node):
    if node.tag in JUNK:
        return True
    a = node.attrs
    return (
        "hidden" in a
        or a.get("aria-hidden", "").lower() == "true"
        or bool(HIDDEN_STYLE.search(a.get("style", "")))
    )


def landmark(node, inside_main):
    role = node.attrs.get("role", "").lower()
    if node.tag in LANDMARKS or role in LANDMARK_ROLES:
        return True
    # A page header is furniture; an article's own header carries its title.
    return node.tag == "header" and not inside_main


def unlikely(node):
    if node.tag in ("body", "html", "article", "main", "a"):
        return False
    words = node.attrs.get("class", "") + " " + node.attrs.get("id", "")
    return bool(UNLIKELY.search(words)) and not MAYBE.search(words)


class Page:
    """One parsed document with the bookkeeping the article search needs."""

    def __init__(self, root):
        self.root = root
        self.body = find(root, "body") or root
        self.drop = set()  # never content
        self.furniture = set()  # landmarks: dropped in both readings
        self.unlikely = set()  # dropped only when reading an article
        self._mark(self.body, False)
        self._text = {}
        self._links = {}

    def _mark(self, top, inside_main):
        stack = [(top, inside_main)]
        while stack:
            node, inside = stack.pop()
            for ch in node.kids():
                if junk(ch):
                    self.drop.add(id(ch))
                    continue
                if landmark(ch, inside):
                    self.furniture.add(id(ch))
                    continue
                if unlikely(ch):
                    self.unlikely.add(id(ch))
                stack.append((ch, inside or ch.tag in ("main", "article")))

    def skipped(self, node, article):
        key = id(node)
        return (
            key in self.drop
            or key in self.furniture
            or (article and key in self.unlikely)
        )

    def text_len(self, node, article=True):
        """Visible characters below `node`; also counts those inside links."""
        key = (id(node), article)
        if key not in self._text:
            total = links = 0
            stack = [(node, False)]
            while stack:
                current, in_link = stack.pop()
                for ch in current.children:
                    if ch.tag is None:
                        n = len(collapse(ch.text).strip())
                        total += n
                        links += n if in_link else 0
                    elif not self.skipped(ch, article):
                        stack.append((ch, in_link or ch.tag == "a"))
            self._text[key], self._links[key] = total, links
        return self._text[key]

    def link_density(self, node, article=True):
        total = self.text_len(node, article)
        return self._links[(id(node), article)] / total if total else 0.0


def _class_weight(node):
    words = node.attrs.get("class", "") + " " + node.attrs.get("id", "")
    weight = 0
    if POSITIVE.search(words):
        weight += 25
    if NEGATIVE.search(words):
        weight -= 25
    return weight


def _base_score(node):
    base = {
        "div": 5,
        "article": 8,
        "main": 8,
        "section": 3,
        "pre": 3,
        "td": 3,
        "blockquote": 3,
    }
    penalty = {"address", "ol", "ul", "dl", "dd", "dt", "li", "form", "th"}
    score = base.get(node.tag, 0) - (3 if node.tag in penalty else 0)
    if node.tag in HEADINGS:
        score -= 5
    return score + _class_weight(node)


def _has_block(node):
    return any(ch.tag in BLOCK for ch in node.kids())


def article(page):
    """The nodes that hold the piece itself, in document order, or None.

    The usual readability approach: score the containers of paragraph-like text,
    discount link-heavy ones, take the best, and keep siblings that read like part
    of the same piece."""
    scores = {}
    nodes = {}
    for node in visible(page, page.body):
        if node.tag not in ("p", "pre", "td", "blockquote") and not (
            node.tag == "div" and not _has_block(node)
        ):
            continue
        length = page.text_len(node)
        if length < 25:
            continue
        text = _plain(page, node)
        points = 1 + text.count(",") + text.count("，") + min(length // 100, 3)
        for level, anc in enumerate(_ancestors(node, page.body, limit=3)):
            if anc.tag in ("#root",):
                break
            if id(anc) not in scores:
                scores[id(anc)] = _base_score(anc)
                nodes[id(anc)] = anc
            scores[id(anc)] += points / (
                1 if level == 0 else 2 if level == 1 else level * 3
            )
    if not scores:
        return None
    ranked = {k: v * (1 - page.link_density(nodes[k])) for k, v in scores.items()}
    best_id = max(ranked, key=ranked.get)
    best = nodes[best_id]
    parent = best.parent
    if parent is None or best is page.body:
        return [best]
    threshold = max(10.0, ranked[best_id] * 0.2)
    kept = []
    for sib in parent.kids():
        if page.skipped(sib, True):
            continue
        if sib is best:
            kept.append(sib)
            continue
        bonus = (
            ranked[best_id] * 0.2
            if sib.attrs.get("class")
            and sib.attrs.get("class") == best.attrs.get("class")
            else 0
        )
        if ranked.get(id(sib), 0) + bonus >= threshold:
            kept.append(sib)
        elif sib.tag == "p":
            length = page.text_len(sib)
            density = page.link_density(sib)
            if (length > 80 and density < 0.25) or (
                0 < length <= 80
                and density == 0
                and re.search(r"\.( |$)", _plain(page, sib))
            ):
                kept.append(sib)
    return kept


def _ancestors(node, stop, limit=None):
    out = []
    current = node.parent
    while current is not None and (limit is None or len(out) < limit):
        out.append(current)
        if current is stop:
            break
        current = current.parent
    return out


def _plain(page, node, article=True):
    return collapse(" ".join(_ordered_text(page, node, article))).strip()


def _ordered_text(page, node, article):
    stack = [iter(node.children)]
    while stack:
        try:
            ch = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if ch.tag is None:
            yield ch.text
        elif not page.skipped(ch, article):
            stack.append(iter(ch.children))


def visible(page, node, article=True):
    """Elements below `node` that are not skipped, without entering skipped ones."""
    stack = [iter(node.kids())]
    while stack:
        try:
            ch = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if page.skipped(ch, article):
            continue
        yield ch
        stack.append(iter(ch.kids()))


class Markdown:
    """Element tree to Markdown: headings, paragraphs, lists, quotes, code, tables,
    links and images, with whitespace collapsed the way a browser renders it."""

    def __init__(self, page, base, article):
        self.page = page
        self.base = base
        self.article = article

    def skip(self, node):
        if self.page.skipped(node, self.article):
            return True
        # Inside an article, a short block that is mostly links is a list of
        # elsewhere (related stories, tags, share buttons), not part of the piece.
        if self.article and node.tag in ("ul", "ol", "div", "section", "table"):
            length = self.page.text_len(node)
            return (
                0 < length < 400
                and self.page.link_density(node) > 0.6
                and sum(1 for n in visible(self.page, node) if n.tag == "a") >= 3
            )
        return False

    def url(self, value):
        value = (value or "").strip()
        if not value or value.startswith(
            ("javascript:", "data:", "mailto:", "tel:", "#")
        ):
            return ""
        try:
            return urljoin(self.base, value)
        except ValueError:
            return ""

    def image(self, node):
        a = node.attrs
        src = a.get("src") or a.get("data-src") or a.get("data-original") or ""
        if not src and a.get("srcset"):
            src = a["srcset"].split(",")[0].strip().split(" ")[0]
        src = self.url(src)
        if not src or src.lower().split("?")[0].endswith((".svg", ".gif")):
            return ""
        if a.get("width") in ("0", "1", "2") or a.get("height") in ("0", "1", "2"):
            return ""
        alt = collapse(a.get("alt", "")).strip().replace("]", ")")
        return f"![{alt or 'image'}]({src})"

    def inline(self, node, code=False):
        if node.tag is None:
            return node.text if code else collapse(node.text)
        if self.skip(node):
            return ""
        tag = node.tag
        if tag == "br":
            return "\n"
        if tag == "img":
            return self.image(node)
        if tag in ("ul", "ol", "table", "pre", "blockquote") and not code:
            return " " + " ".join(self.blocks(node)) + " "
        inner = "".join(self.inline(ch, code or tag == "code") for ch in node.children)
        if tag == "a" and not code:
            text = inner.strip()
            href = self.url(node.attrs.get("href"))
            if not text:
                return ""
            if not href or text == href:
                return inner
            return _wrap(inner, "[", f"]({href})")
        if tag in ("strong", "b") and not code:
            return _wrap(inner, "**", "**")
        if tag in ("em", "i") and not code:
            return _wrap(inner, "*", "*")
        if tag == "code" and not code:
            return _wrap(inner, "`", "`")
        if tag in BLOCK:
            return " " + inner + " "
        return inner

    def blocks(self, node):
        out, run = [], []

        def flush():
            text = _tidy("".join(run))
            run.clear()
            if text:
                out.append(text)

        for ch in node.children:
            if ch.tag is not None and self.skip(ch):
                continue
            if ch.tag is not None and (ch.tag in BLOCK or ch.tag == "pre"):
                flush()
                out.extend(self.block(ch))
            else:
                run.append(self.inline(ch))
        flush()
        return out

    def block(self, node):
        tag = node.tag
        if tag in HEADINGS:
            text = _tidy(self.inline(node)).replace("\n", " ")
            return [("#" * HEADINGS[tag]) + " " + text] if text else []
        if tag == "p":
            text = _tidy(self.inline(node))
            return [text] if text else []
        if tag == "pre":
            code = "".join(self.inline(ch, code=True) for ch in node.children)
            code = code.strip("\n")
            if not code.strip():
                return []
            lang = ""
            for name in (
                node.attrs.get("class", ""),
                *(c.attrs.get("class", "") for c in node.kids()),
            ):
                match = re.search(r"(?:language|lang)-([\w+#-]+)", name)
                if match:
                    lang = match.group(1)
                    break
            return [f"```{lang}\n{code}\n```"]
        if tag in ("ul", "ol", "menu", "dir"):
            text = self.listing(node, tag == "ol")
            return [text] if text else []
        if tag == "li":
            text = self.item(node, "-", "  ")
            return [text] if text else []
        if tag == "blockquote":
            inner = "\n\n".join(self.blocks(node))
            return (
                ["\n".join("> " + line if line else ">" for line in inner.split("\n"))]
                if inner
                else []
            )
        if tag == "table":
            return self.table(node)
        if tag == "hr":
            return ["---"]
        if tag == "dl":
            lines = []
            for ch in node.kids():
                if self.skip(ch):
                    continue
                text = _tidy(self.inline(ch))
                if text and ch.tag == "dt":
                    lines.append(f"**{text}**")
                elif text:
                    lines.append(text)
            return ["\n".join(lines)] if lines else []
        if tag == "figcaption":
            text = _tidy(self.inline(node))
            return [f"*{text}*"] if text else []
        return self.blocks(node)

    def item(self, node, marker, indent):
        parts = self.blocks(node)
        if not parts:
            return ""
        lines = [marker + " " + parts[0].replace("\n", "\n" + indent)]
        lines += [indent + p.replace("\n", "\n" + indent) for p in parts[1:]]
        return "\n".join(lines)

    def listing(self, node, ordered):
        number = 1
        if ordered:
            try:
                number = int(node.attrs.get("start") or 1)
            except ValueError:
                number = 1
        items = []
        for ch in node.children:
            if ch.tag is None:
                if collapse(ch.text).strip():
                    items.append("- " + collapse(ch.text).strip())
                continue
            if self.skip(ch):
                continue
            if ch.tag != "li":
                items.extend(
                    self.block(ch) if ch.tag in BLOCK else [_tidy(self.inline(ch))]
                )
                continue
            marker = f"{number}." if ordered else "-"
            text = self.item(ch, marker, " " * (len(marker) + 1))
            if text:
                items.append(text)
                number += 1
        return "\n".join(i for i in items if i)

    def table(self, node):
        rows, header = [], False
        for tr in _rows(node):
            cells = [c for c in tr.kids() if c.tag in ("td", "th") and not self.skip(c)]
            if not cells:
                continue
            if not rows and all(c.tag == "th" for c in cells):
                header = True
            rows.append(
                [
                    _tidy(self.inline(c)).replace("\n", " ").replace("|", "\\|")
                    for c in cells
                ]
            )
        width = max((len(r) for r in rows), default=0)
        texts = [len(cell) for row in rows for cell in row]
        data = (
            width >= 2
            and find(node, "table") is None
            and (header or find(node, "caption") is not None or len(rows) >= 3)
            and (sum(texts) / len(texts) if texts else 0) <= 200
        )
        if not data:
            return self.blocks(node)
        lines = []
        caption = find(node, "caption")
        if caption is not None:
            text = _tidy(self.inline(caption))
            if text:
                lines.append(f"*{text}*")
        for i, row in enumerate(rows):
            row = row + [""] * (width - len(row))
            lines.append("| " + " | ".join(row) + " |")
            if i == 0:
                lines.append("|" + "---|" * width)
        return ["\n".join(lines)]


def _rows(table):
    for ch in table.kids():
        if ch.tag == "tr":
            yield ch
        elif ch.tag in ("thead", "tbody", "tfoot"):
            yield from (r for r in ch.kids() if r.tag == "tr")


def _wrap(inner, left, right):
    match = re.match(r"(\s*)(.*?)(\s*)$", inner, re.S)
    lead, core, trail = match.groups()
    return f"{lead}{left}{core}{right}{trail}" if core else inner


def _tidy(text):
    lines = [collapse(line).strip() for line in text.split("\n")]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _meta(root):
    found = {}
    for node in walk(root):
        if node.tag == "meta":
            key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
            if key and "content" in node.attrs and key not in found:
                found[key] = collapse(node.attrs["content"]).strip()
        elif node.tag == "link" and "canonical" in node.attrs.get("rel", "").lower():
            found.setdefault("canonical", node.attrs.get("href", ""))
        elif node.tag == "title" and "title" not in found:
            found["title"] = collapse(
                "".join(ch.text for ch in node.children if ch.tag is None)
            ).strip()
        elif node.tag == "html" and node.attrs.get("lang"):
            found.setdefault("lang", node.attrs["lang"])
    return found


def html_to_markdown(markup, base_url=""):
    """Readable Markdown for one HTML document: (title, content, metadata).

    The piece itself when one can be found; otherwise, or when that finds too little
    of the page (a forum thread, a listing), the whole page without its furniture."""
    root = parse(markup)
    page = Page(root)
    meta = _meta(root)
    whole_len = page.text_len(page.body, article=False)
    chosen = article(page)
    content = ""
    mode = "page"
    # The piece is trusted when it is substantial or most of the page; a sliver of
    # a long page (one post of a thread, the intro of a listing) is not the page.
    found = sum(page.text_len(node) for node in chosen or [])
    try:
        if chosen and found >= THIN and (found >= 1500 or found >= 0.25 * whole_len):
            render = Markdown(page, base_url, True)
            content = "\n\n".join(b for node in chosen for b in render.block(node) if b)
            mode = "article"
        if not content:
            content = "\n\n".join(Markdown(page, base_url, False).blocks(page.body))
            mode = "page"
    except RecursionError:
        content, mode = _plain(page, page.body, False), "text"
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    title = meta.get("og:title") or meta.get("twitter:title") or meta.get("title") or ""
    if not title:
        heading = find(page.body, "h1")
        title = _plain(page, heading, False) if heading is not None else ""
    published = meta.get("article:published_time") or meta.get("date") or ""
    if not published:
        stamp = find(page.body, "time")
        published = stamp.attrs.get("datetime", "") if stamp is not None else ""
    metadata = {
        k: v
        for k, v in {
            "description": meta.get("og:description") or meta.get("description") or "",
            "site_name": meta.get("og:site_name") or "",
            "author": meta.get("author") or meta.get("article:author") or "",
            "published": published,
            "language": meta.get("lang") or "",
            "canonical": meta.get("canonical") or "",
            "reading": mode,
        }.items()
        if v
    }
    return title, content[:MAX_CONTENT_CHARS], metadata


def feed_to_markdown(text):
    """An RSS or Atom feed as a list of its entries, or None when it is not one."""
    import xml.etree.ElementTree as ET

    # Entity definitions live in the DOCTYPE; without it nothing can expand.
    text = re.sub(
        r"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", "", text, count=1, flags=re.S | re.I
    )
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError:
        return None

    def local(tag):
        return tag.rsplit("}", 1)[-1].lower()

    def child(el, *names):
        for ch in el:
            if local(ch.tag) in names:
                return ch
        return None

    def text_of(el):
        if el is None:
            return ""
        value = "".join(el.itertext())
        return collapse(re.sub(r"<[^>]+>", " ", value)).strip()

    kind = local(root.tag)
    if kind == "rss":
        channel = child(root, "channel")
        if channel is None:
            return None
        title, entries = text_of(child(channel, "title")), [
            e for e in channel if local(e.tag) == "item"
        ]
    elif kind == "feed":
        title, entries = text_of(child(root, "title")), [
            e for e in root if local(e.tag) == "entry"
        ]
    elif kind == "rdf":
        channel = child(root, "channel")
        title = text_of(child(channel, "title")) if channel is not None else ""
        entries = [e for e in root if local(e.tag) == "item"]
    else:
        return None
    lines = []
    for entry in entries[:MAX_FEED_ITEMS]:
        name = text_of(child(entry, "title")) or "(untitled)"
        link_el = child(entry, "link")
        link = ""
        if link_el is not None:
            link = (link_el.get("href") or text_of(link_el)).strip()
        when = text_of(child(entry, "pubdate", "published", "updated", "date"))
        summary = text_of(child(entry, "description", "summary", "content"))
        line = f"- [{name}]({link})" if link else f"- {name}"
        if when:
            line += f" — {when}"
        if summary:
            line += "\n  " + (summary[:300] + "…" if len(summary) > 300 else summary)
        lines.append(line)
    more = len(entries) - MAX_FEED_ITEMS
    if more > 0:
        lines.append(f"- … {more} more entries")
    return title, "\n".join(lines)


def decode(body, content_type):
    match = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", content_type or "", re.I)
    candidates = [match.group(1)] if match else []
    sniff = CHARSET.search(body[:4096])
    if sniff:
        candidates.append(sniff.group(1).decode("ascii", "replace"))
    candidates.append("utf-8")
    for name in candidates:
        try:
            return body.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(body).best()
        if best is not None:
            return str(best)
    except Exception:  # noqa: BLE001 -- optional; fall through to a lossy decode
        pass
    return body.decode("utf-8", "replace")


def _name_of(url):
    path = urlsplit(url).path.rstrip("/")
    return unquote(path.rsplit("/", 1)[-1]) or urlsplit(url).hostname or url


def render(url, final_url, status, content_type, body, truncated=False):
    """One fetched response as a web_extract result entry."""
    kind = (content_type or "").split(";")[0].strip().lower()
    head = body[:2048].lstrip().lower()
    entry = {"url": url, "title": "", "content": "", "metadata": {}}
    meta = entry["metadata"]
    meta.update(
        sourceURL=url,
        status=status,
        content_type=kind or "unknown",
        reader="this machine",
    )
    if final_url and final_url != url:
        meta["final_url"] = final_url
    if truncated:
        meta["truncated"] = (
            f"only the first {MAX_BYTES // (1024 * 1024)} MB were downloaded"
        )
    looks_html = head.startswith((b"<!doctype html", b"<html")) or b"<body" in head
    if kind in ("application/pdf",) or head.startswith(b"%pdf"):
        try:
            from tools.read_extract import extract_document_bytes

            entry["content"] = extract_document_bytes(body, "page.pdf")
            entry["title"] = _name_of(final_url or url)
        except Exception:  # noqa: BLE001 -- no PDF converter on this machine
            entry["error"] = (
                "This link is a PDF, and there is no PDF reader on this machine for pages. "
                + BROWSER_HINT
            )
        return entry
    # Servers often call text "octet-stream"; only bytes that are not text are refused.
    archive = ("application/zip", "application/gzip", "application/x-tar")
    if (
        kind.startswith(("image/", "audio/", "video/", "font/"))
        or kind in archive
        or b"\x00" in body[:2048]
    ):
        entry["error"] = f"This link is not a page to read ({kind or 'binary data'})."
        return entry
    text = decode(body, content_type)
    if kind in ("application/json",) or kind.endswith("+json"):
        try:
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except ValueError:
            pass
        entry.update(title=_name_of(final_url or url), content=text[:MAX_CONTENT_CHARS])
        return entry
    if (
        kind.endswith(("+xml", "/xml", "/rss", "/atom"))
        or head.startswith(b"<?xml")
        or b"<rss" in head
        or b"<feed" in head
    ) and not looks_html:
        feed = feed_to_markdown(text)
        if feed is not None:
            entry["title"], entry["content"] = feed
            meta["reading"] = "feed"
            return entry
        if "html" not in kind:
            entry.update(
                title=_name_of(final_url or url), content=text[:MAX_CONTENT_CHARS]
            )
            return entry
    if kind.startswith("text/") and "html" not in kind and not looks_html:
        entry.update(title=_name_of(final_url or url), content=text[:MAX_CONTENT_CHARS])
        return entry
    title, content, extra = html_to_markdown(text, final_url or url)
    meta.update(extra)
    entry.update(title=title, content=content)
    if len(content) < THIN:
        entry["error"] = (
            "The page has almost no readable text without running its scripts. "
            + BROWSER_HINT
        )
    return entry


def _failure(url, message):
    return {"url": url, "title": "", "content": "", "error": message}


def _explain(exc):
    name = type(exc).__name__
    text = str(exc)
    if "SSRF" in name or "Blocked" in text:
        return "Blocked: that address is on a private or internal network."
    if "Timeout" in name:
        return f"The site did not answer within {int(TIMEOUT)} seconds."
    if "TooManyRedirects" in name:
        return "The site redirected too many times."
    if (
        "ConnectError" in name
        or "gaierror" in text
        or "Name or service not known" in text
    ):
        return "The site could not be reached from this machine."
    return f"The page could not be fetched ({name})."


async def fetch(client, url):
    """GET one URL, reading at most MAX_BYTES. Returns a result entry."""
    try:
        async with client.stream("GET", url, headers=HEADERS) as response:
            final = str(response.url)
            if urlsplit(final).scheme not in ("http", "https"):
                return _failure(
                    url, "The page redirected somewhere that is not a web address."
                )
            chunks, size, truncated = [], 0, False
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= MAX_BYTES:
                    truncated = True
                    break
            body = b"".join(chunks)[:MAX_BYTES]
            status = response.status_code
            content_type = response.headers.get("content-type", "")
    except Exception as exc:  # noqa: BLE001 -- every failure is one URL's answer
        return _failure(url, _explain(exc))
    entry = render(url, final, status, content_type, body, truncated)
    if status >= 400:
        reason = {
            401: "it needs a login",
            403: "it refused an automated reader",
            404: "the page was not found",
            410: "the page is gone",
            429: "it is limiting requests right now",
        }.get(status, "it returned an error")
        hint = " " + BROWSER_HINT if status in (401, 403, 429) else ""
        entry["error"] = f"The site answered {status}: {reason}.{hint}"
    return entry


async def read(urls, client_factory=None):
    """Read each URL on this machine; one result entry per URL, in order."""
    if client_factory is None:
        import httpx

        client_factory = httpx.AsyncClient
    async with client_factory(
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        timeout=TIMEOUT,
        headers=HEADERS,
    ) as client:
        tasks = [fetch(client, str(u)) for u in urls]
        return list(await asyncio.gather(*tasks))
