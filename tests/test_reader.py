"""Web pages read on this machine: the text a page yields, and the plugin that
puts the reader in front of Hermes's web_extract."""

import asyncio
import http.server
import importlib.util
import json
import pathlib
import sys
import tempfile
import threading
import types
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "kit/scripts"), str(ROOT)]

import companion_config as cc  # noqa: E402
import companion_reader as reader  # noqa: E402
import companion_routing as routing  # noqa: E402

ARTICLE = """<!doctype html><html lang="en"><head><title>Kettle notes | Example</title>
<meta property="og:site_name" content="Example"><meta name="description" content="On kettles.">
<script>var x = "<p>not this</p>";</script><style>p{color:red}</style></head>
<body><header class="site-header"><nav><a href="/">Home</a> <a href="/about">About</a></nav></header>
<div class="cookie-banner">We use cookies <button>OK</button></div>
<main><article class="post"><header><h1>Why a kettle ticks</h1>
<time datetime="2026-03-01">1 March</time></header>
<p>A kettle ticks as it heats because the metal expands unevenly, and the base, the
walls, and the lid all move at different rates.
<p>That sound, familiar to anyone who has waited for tea, is the steel <em>relieving
stress</em>, not a fault; see <a href="/physics">the physics</a>.</p>
<ul><li>Base heats first<li>Walls follow<ul><li>Lid last</li></ul></ul>
<pre><code class="language-python">print("hi")
    indented()</code></pre>
<table><tr><th>Part</th><th>Order</th></tr><tr><td>Base</td><td>1</td></tr></table>
<blockquote><p>Patience is a kettle.</p></blockquote>
<div class="share"><a href="/x">Share</a> <a href="/y">Post</a> <a href="/z">Mail</a></div>
<img src="/img/kettle.jpg" alt="A steel kettle"></article></main>
<aside><h3>Related</h3><a href="/r1">Toasters</a></aside><footer>(c) Example</footer>
</body></html>"""


def thread_page(posts):
    rows = "".join(
        f'<tr class="comment-row"><td class="comment">Reply {i}: '
        + "a thoughtful, longish reply about kettles, steel, and patience. " * 3
        + "</td></tr>"
        for i in range(posts)
    )
    return (
        "<html><body><table><tr><td><p>Ask: why do kettles tick? It is a short "
        "question, asked in passing.</p></td></tr></table>"
        f'<table class="comment-tree">{rows}</table></body></html>'
    )


class MarkdownTests(unittest.TestCase):
    def test_an_article_reads_as_the_piece_without_the_site(self):
        title, content, meta = reader.html_to_markdown(
            ARTICLE, "https://example.org/notes/kettle"
        )
        self.assertEqual(title, "Kettle notes | Example")
        self.assertEqual(meta["reading"], "article")
        self.assertEqual(meta["published"], "2026-03-01")
        self.assertEqual(meta["site_name"], "Example")
        self.assertIn("# Why a kettle ticks", content)
        self.assertIn("*relieving stress*", content)
        self.assertIn("[the physics](https://example.org/physics)", content)
        self.assertIn("- Base heats first\n- Walls follow\n  - Lid last", content)
        self.assertIn('```python\nprint("hi")\n    indented()\n```', content)
        self.assertIn("| Part | Order |\n|---|---|\n| Base | 1 |", content)
        self.assertIn("> Patience is a kettle.", content)
        self.assertIn("![A steel kettle](https://example.org/img/kettle.jpg)", content)
        for furniture in (
            "not this",
            "color:red",
            "cookies",
            "About",
            "Toasters",
            "Share",
            "(c) Example",
        ):
            self.assertNotIn(furniture, content)

    def test_a_thread_is_read_whole_rather_than_one_sliver(self):
        _, content, meta = reader.html_to_markdown(
            thread_page(12), "https://forum.test/t/1"
        )
        self.assertEqual(meta["reading"], "page")
        self.assertIn("Ask: why do kettles tick?", content)
        self.assertIn("Reply 11:", content)

    def test_a_script_built_page_points_at_the_browser(self):
        entry = reader.render(
            "https://app.test/", "https://app.test/", 200, "text/html",
            b'<html><body><div id="root"></div><script src="app.js"></script></body></html>',
        )  # fmt: skip
        self.assertIn("browser_navigate", entry["error"])

    def test_feeds_list_their_entries(self):
        feed = (
            b'<?xml version="1.0" encoding="ISO-8859-1"?><rss version="2.0"><channel>'
            b"<title>News</title><item><title>One</title><link>https://n.test/1</link>"
            b"<pubDate>Thu, 05 Mar 2026</pubDate><description>&lt;p&gt;First &amp; best"
            b"&lt;/p&gt;</description></item></channel></rss>"
        )
        # Servers often call a feed octet-stream; the bytes decide.
        entry = reader.render(
            "https://n.test/rss",
            "https://n.test/rss",
            200,
            "application/octet-stream",
            feed,
        )
        self.assertEqual(entry["title"], "News")
        self.assertIn(
            "- [One](https://n.test/1) — Thu, 05 Mar 2026\n  First & best",
            entry["content"],
        )

    def test_a_feed_cannot_define_entities(self):
        bomb = (
            b'<?xml version="1.0"?><!DOCTYPE z [<!ENTITY a "aaaaaaaaaa">'
            b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            b"<rss><channel><title>&b;</title></channel></rss>"
        )
        entry = reader.render(
            "https://n.test/b", "https://n.test/b", 200, "application/xml", bomb
        )
        self.assertNotIn("aaaaaaaaaaaaaaaaaaaa", entry["content"])

    def test_json_text_and_binary(self):
        entry = reader.render(
            "https://a.test/x.json",
            "https://a.test/x.json",
            200,
            "application/json",
            b'{"a":[1]}',
        )
        self.assertEqual(json.loads(entry["content"]), {"a": [1]})
        entry = reader.render(
            "https://a.test/n.txt",
            "https://a.test/n.txt",
            200,
            "text/plain; charset=utf-8",
            "naïve".encode(),
        )
        self.assertEqual(entry["content"], "naïve")
        entry = reader.render(
            "https://a.test/p.png",
            "https://a.test/p.png",
            200,
            "image/png",
            b"\x89PNG\x00\x00",
        )
        self.assertIn("not a page to read", entry["error"])

    def test_declared_and_sniffed_charsets(self):
        latin = "<html><body><p>café " + "x" * 300 + "</p></body></html>"
        entry = reader.render(
            "https://a.test/",
            "https://a.test/",
            200,
            "text/html; charset=iso-8859-1",
            latin.encode("latin-1"),
        )
        self.assertIn("café", entry["content"])
        sniffed = (
            '<html><head><meta charset="windows-1252"></head><body><p>“quoted” '
            + "y" * 300
            + "</p></body></html>"
        )
        entry = reader.render(
            "https://a.test/",
            "https://a.test/",
            200,
            "text/html",
            sniffed.encode("cp1252"),
        )
        self.assertIn("“quoted”", entry["content"])

    def test_pathological_nesting_does_not_crash(self):
        deep = "<div>" * 5000 + "<p>" + "deep text, " * 40 + "</p>" + "</div>" * 5000
        _, content, _ = reader.html_to_markdown(deep, "https://a.test/")
        self.assertIn("deep text", content)


class Pages(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/moved":
            self.send_response(302)
            self.send_header("Location", "/article")
            self.end_headers()
            return
        if self.path == "/missing":
            body, status = b"<html><body><p>Not here.</p></body></html>", 404
        elif self.path == "/huge":
            body, status = (
                b"<html><body><p>"
                + b"z" * (reader.MAX_BYTES + 4096)
                + b"</p></body></html>",
                200,
            )
        else:
            body, status = ARTICLE.encode(), 200
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pages)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_one_entry_per_url_in_order_under_the_requested_url(self):
        urls = [
            self.base + "/moved",
            self.base + "/missing",
            "http://unreachable.invalid/",
        ]
        results = asyncio.run(reader.read(urls))
        self.assertEqual([r["url"] for r in results], urls)
        moved, missing, unreachable = results
        self.assertIn("# Why a kettle ticks", moved["content"])
        self.assertEqual(moved["metadata"]["final_url"], self.base + "/article")
        self.assertEqual(moved["metadata"]["sourceURL"], urls[0])
        self.assertIn("404", missing["error"])
        self.assertIn("could not be reached", unreachable["error"])

    def test_downloads_stop_at_the_limit(self):
        (entry,) = asyncio.run(reader.read([self.base + "/huge"]))
        self.assertIn("truncated", entry["metadata"])
        self.assertLessEqual(len(entry["content"]), reader.MAX_CONTENT_CHARS)

    def test_the_client_comes_from_the_factory_given(self):
        import httpx

        made = []

        def factory(**kwargs):
            made.append(kwargs)
            return httpx.AsyncClient(**kwargs)

        asyncio.run(reader.read([self.base + "/article"], client_factory=factory))
        self.assertEqual(len(made), 1)
        self.assertTrue(made[0]["follow_redirects"])


def load_plugin(fake_modules):
    """Import the plugin package as Hermes would, against stand-ins for Hermes."""
    saved = {name: sys.modules.get(name) for name in fake_modules}
    sys.modules.update(fake_modules)
    try:
        folder = ROOT / "kit/plugins/tamanitomo-reader"
        spec = importlib.util.spec_from_file_location(
            "tamanitomo_reader_plugin",
            folder / "__init__.py",
            submodule_search_locations=[str(folder)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        # Installed beside it as reader.py; the source lives in kit/scripts.
        sys.modules[spec.name + ".reader"] = reader
        spec.loader.exec_module(module)
        registered = []
        module.register(
            types.SimpleNamespace(register_web_search_provider=registered.append)
        )
        return registered[0], saved
    except Exception:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        raise


class PluginTests(unittest.TestCase):
    def setUp(self):
        class WebSearchProvider:
            pass

        self.factory = object()
        provider_mod = types.ModuleType("agent.web_search_provider")
        provider_mod.WebSearchProvider = WebSearchProvider
        safety = types.ModuleType("tools.url_safety")
        safety.create_ssrf_safe_async_client = self.factory
        self.provider, self.saved = load_plugin(
            {
                "agent": types.ModuleType("agent"),
                "agent.web_search_provider": provider_mod,
                "tools": types.ModuleType("tools"),
                "tools.url_safety": safety,
            }
        )

    def tearDown(self):
        for name, old in self.saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old

    def test_reads_only_and_only_when_named(self):
        p = self.provider
        self.assertEqual(p.name, "tamanitomo-reader")
        self.assertTrue(p.supports_extract())
        self.assertFalse(p.supports_search())
        # "Available" would let Hermes's search autodetection pick an extract-only
        # provider and leave the companion unable to search.
        self.assertFalse(p.is_available())

    def test_extract_uses_hermess_ssrf_safe_client(self):
        seen = {}

        async def fake_read(urls, client_factory=None):
            seen.update(urls=urls, factory=client_factory)
            return []

        original = reader.read
        reader.read = fake_read
        try:
            asyncio.run(self.provider.extract(["https://a.test/"], format="markdown"))
        finally:
            reader.read = original
        self.assertIs(seen["factory"], self.factory)


class EnrollmentTests(unittest.TestCase):
    def test_reads_here_unless_another_reader_was_chosen(self):
        cases = [
            ({}, {}, True),
            ({"web": {"backend": "searxng", "extract_backend": ""}}, {}, True),
            ({"web": {"extract_backend": "firecrawl"}}, {}, False),
            ({"web": {"backend": "tavily"}}, {}, False),
            ({}, {"EXA_API_KEY": "k"}, False),
            ({"web": {"use_gateway": True}}, {}, False),
        ]
        for cfg, env, expected in cases:
            with self.subTest(cfg=cfg, env=env):
                self.assertEqual(routing.enroll_reader(cfg, env), expected)
                if expected:
                    self.assertEqual(cfg["web"]["extract_backend"], "tamanitomo-reader")
                    self.assertIs(cfg["web"]["keyless_rescue"], False)
                    self.assertIn("tamanitomo-reader", cfg["plugins"]["enabled"])
                    # Search is never touched.
                    self.assertNotIn("search_backend", cfg["web"])

    def test_the_apps_switch_overrides_and_hands_back(self):
        cfg = {"web": {"extract_backend": "firecrawl"}}
        self.assertTrue(routing.enroll_reader(cfg, {}, force=True))
        self.assertTrue(routing.reads_locally(cfg))
        routing.retire_reader(cfg)
        self.assertFalse(routing.reads_locally(cfg))
        self.assertNotIn("keyless_rescue", cfg["web"])

    def test_install_and_the_switch_on_a_profile(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        c = cc.Companion(agent="Nova", human="Robin", profile="nova",
                         hermes_root=tmp / ".hermes", vault=tmp / "vault")  # fmt: skip
        c.home.mkdir(parents=True)
        (c.home / "config.yaml").write_text(
            yaml.safe_dump({"web": {"backend": "searxng"}})
        )
        self.assertTrue(routing.install(c), "a new plugin needs a gateway restart")
        self.assertFalse(routing.install(c), "nothing changed the second time")
        plugin = c.home / "plugins/tamanitomo-reader"
        self.assertEqual(
            (plugin / "reader.py").read_bytes(),
            (ROOT / "kit/scripts/companion_reader.py").read_bytes(),
        )
        self.assertTrue(routing.reader_status(c)["local"])
        routing.set_reader(c, False)
        self.assertEqual(routing.reader_status(c), {"local": False, "other": ""})
        cfg = yaml.safe_load((c.home / "config.yaml").read_text())
        self.assertEqual(cfg["web"]["backend"], "searxng")
        # Switched off in the app, a later repair leaves it off.
        c.local_web_reader = False
        routing.install(c)
        self.assertFalse(routing.reader_status(c)["local"])


if __name__ == "__main__":
    unittest.main()
