"""Character budgets fit the reading model's tokenizer: Claude spends a token per ~2.5 chars."""

import pathlib
import sys
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
import companion_context as context  # noqa: E402


def test_the_same_tokens_hold_fewer_characters_on_claude():
    assert cc.chars_per_token("claude-sonnet-5-5") == 2.5
    assert cc.chars_per_token("anthropic/claude-haiku-5-5") == 2.5
    assert cc.chars_per_token("gpt-6.2-sol") == 4.0
    assert cc.budget_scale(None) == 1.0
    c = cc.Companion(agent="Nova", human="Robin", context_tokens=272000)
    full, claude = c.budgets(), c.budgets(scale=cc.budget_scale("claude-haiku-5-5"))
    assert claude["total"] == int(full["total"] * 0.625)
    assert claude["facts"] < full["facts"]
    assert claude["rules"] == full["rules"] and claude["tail"] == full["tail"]


def test_the_hook_sizes_for_the_model_that_will_read_it(tmp_path):
    c = cc.Companion(
        agent="Nova",
        human="Robin",
        hermes_root=tmp_path / "h",
        vault=tmp_path / "v",
        context_tokens=272000,
    )
    c.home.mkdir(parents=True)
    seen = []
    real = cc.Companion.budgets

    def spy(self, scale=1.0):
        seen.append(scale)
        return real(self, scale=scale)

    with mock.patch.object(cc.Companion, "budgets", spy):
        context.build(
            c, {"extra": {"user_message": "hi", "model": "claude-sonnet-5-5"}}
        )
        context.build(c, {"extra": {"user_message": "hi", "model": "gpt-6.2-sol"}})
    assert seen[:2] == [0.625, 1.0]
