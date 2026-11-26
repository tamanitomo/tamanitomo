"""Her internal name is locked in the editor: renaming it duplicated every scheduled job."""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kit/scripts"))

import companion_config as cc  # noqa: E402
from kit.app import profile_editor  # noqa: E402


def test_the_internal_name_is_locked_and_the_display_name_is_the_way_to_rename(
    tmp_path,
):
    c = cc.Companion(
        agent="Nova", human="Robin", hermes_root=tmp_path / "h", vault=tmp_path / "v"
    )
    c.home.mkdir(parents=True)
    c.save()
    snap = profile_editor.snapshot(c)
    assert snap["locked"] == ["agent"]
    config = dict(snap["config"], agent="Vega")
    with pytest.raises(ValueError, match="internal name"):
        profile_editor.save(
            c,
            {
                "revision": snap["revision"],
                "config": config,
                "soul": snap["soul"],
                "display_name": "Vega",
            },
        )
