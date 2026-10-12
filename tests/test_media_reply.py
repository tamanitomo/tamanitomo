"""A photo line written as a Markdown image still arrives as just a photo.

Hermes sends the file named by a `MEDIA:/path` tag and strips the tag from the text.
Wrapped as `![a stretch](MEDIA:/path)`, only the tag went, and `![a stretch]()` was
left in the chat beside every picture. The context plugin unwraps it before delivery."""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def plugin():
    spec = importlib.util.spec_from_file_location(
        "tamanitomo_context_plugin", ROOT / "kit/plugins/tamanitomo-context/__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Hooks:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, callback):
        self.hooks[name] = callback


class MediaReplyTests(unittest.TestCase):
    def setUp(self):
        self.unwrap = plugin().unwrap_media

    def test_a_markdown_image_becomes_the_bare_photo_line(self):
        reply = "Here's one.\n\n![morning stretch](MEDIA:/vault/a.png)\n\nNow tell me."
        self.assertEqual(
            self.unwrap(response_text=reply),
            "Here's one.\n\nMEDIA:/vault/a.png\n\nNow tell me.",
        )

    def test_a_link_spaces_and_angle_brackets_are_unwrapped_too(self):
        reply = "[photo](MEDIA:/vault/a.png) and ![b]( <MEDIA:/vault/b.png> )"
        self.assertEqual(
            self.unwrap(response_text=reply), "MEDIA:/vault/a.png and MEDIA:/vault/b.png"
        )

    def test_everything_else_is_left_alone(self):
        for reply in (
            "",
            "No photo today.",
            "MEDIA:/vault/a.png",
            "![a map](https://example.com/map.png)",
        ):
            self.assertIsNone(self.unwrap(response_text=reply), reply)

    def test_the_plugin_registers_the_hook_without_a_kit_install(self):
        ctx = Hooks()
        module = plugin()
        module.register(ctx)
        self.assertIs(ctx.hooks["transform_llm_output"], module.unwrap_media)


if __name__ == "__main__":
    unittest.main()
