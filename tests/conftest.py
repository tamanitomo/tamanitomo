"""Keep default paths in an isolated home throughout the contract suite."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_user_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("isolated-user-home")
    with pytest.MonkeyPatch.context() as environment:
        for key, value in {
            "HOME": home,
            "USERPROFILE": home,
            "HERMES_HOME": home / ".hermes",
            "LOCALAPPDATA": home / "AppData" / "Local",
            "XDG_CONFIG_HOME": home / ".config",
            "XDG_CACHE_HOME": home / ".cache",
            "XDG_DATA_HOME": home / ".local" / "share",
        }.items():
            environment.setenv(key, str(value))
        environment.delenv("HERMES_PROFILE", raising=False)
        environment.delenv("COMPANION_HOME", raising=False)
        environment.delenv("COMPANION_HERMES_COMMAND", raising=False)
        yield
