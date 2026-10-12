"""The context plugin leaves a companion's finished reply exactly as she wrote it.

It once registered an output transform to unwrap `![alt](MEDIA:/path)`. On a streamed
reply Hermes writes a transformed answer over the message already shown, as raw
text, so the transform put the whole `MEDIA:/path` line into the chat beside every
photo -- where Hermes's own handling would have hidden it."""

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
    def test_the_plugin_rewrites_no_reply(self):
        ctx = Hooks()
        plugin().register(ctx)
        self.assertNotIn("transform_llm_output", ctx.hooks)


if __name__ == "__main__":
    unittest.main()
