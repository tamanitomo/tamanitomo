"""Optional streaming bridge, executed ONLY by Hermes's own Python interpreter.

Keep Hermes's quiet CLI lifecycle, routing, hooks, session persistence and approvals.
If the callback seam changes, retain ordinary final-response behavior.
"""

import contextlib
import io
import json
import os
import sys


def configure_fallbacks(agent, emit):
    """Keep provider recovery inside Hermes's current turn and tool history.

    Re-running the quiet CLI after a timeout can duplicate a user message or a
    completed tool action. Hermes's native recovery loop swaps its client in the
    existing conversation instead. Only the configured chain crosses this seam;
    it never discovers or invents a cloud provider or a local model.
    """
    raw = os.environ.get("TAMANITOMO_CHAT_FALLBACKS")
    if raw is None:
        return
    routes = json.loads(raw)
    if not isinstance(routes, list):
        raise ValueError("Chat fallbacks must be an ordered list")
    # Older Hermes releases may lack the recovery seam. Their own quiet CLI
    # behavior is retained; a changed optional seam must not prevent startup.
    activate = getattr(agent, "_try_activate_fallback", None)
    if not callable(activate):
        return
    agent._fallback_chain = routes
    agent._fallback_index = 0
    agent._fallback_model = routes[0] if routes else None
    if not routes:
        return
    # Fail over promptly instead of exhausting several exponential retry cycles.
    agent._api_max_retries = 1

    def switched(*args, **kwargs):
        result = activate(*args, **kwargs)
        if result:
            emit("fallback")
        return result

    agent._try_activate_fallback = switched


# Imported ahead of the turn by a warm bridge; together ~1.4 s of every turn.
# Plain imports only, nothing that reads config. Names a Hermes release lacks
# are skipped; the openai client loads its submodules lazily, hence the list.
WARM_IMPORTS = (
    "cli",
    "hermes_cli.main",
    "run_agent",
    "model_tools",
    "agent.agent_init",
    "agent.conversation_loop",
    "openai",
    "openai._client",
    "openai.types",
    "openai.resources.chat",
    "openai.lib.streaming",
    "mcp.client.session_group",
    "mcp.client._input_required",
    "tools.tool_search",
    "tools.mcp_oauth",
)


def wait_for_turn():
    """Load Hermes now, then take this process's single turn from stdin.

    The workspace keeps one of these waiting, so a message does not pay for
    interpreter start-up and imports. The turn itself runs exactly as a cold
    one does. An empty line or a closed pipe means the spare was discarded.
    """
    import importlib

    for name in WARM_IMPORTS:
        try:
            importlib.import_module(name)
        except Exception:
            pass  # the turn's own import reports the failure as it always has
    line = sys.stdin.readline()
    if not line.strip():
        raise SystemExit(0)
    turn = json.loads(line)
    if turn.get("fallbacks") is not None:
        os.environ["TAMANITOMO_CHAT_FALLBACKS"] = turn["fallbacks"]
    sys.argv = [sys.argv[0], *turn["args"]]
    # Nothing Hermes runs may read the workspace's pipe; a cold turn has no stdin.
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    sys.stdin = open(os.devnull, encoding="utf-8")


def main():
    wire = sys.stdout

    def emit(kind, **values):
        wire.write(json.dumps({"event": kind, **values}, ensure_ascii=False) + "\n")
        wire.flush()

    output = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(output):
        if sys.argv[1:2] == ["--warm"]:
            wait_for_turn()
        import cli

        # These wrap functions belonging to somebody else's program, which is
        # free to grow an argument without telling us. Both forward whatever
        # they are given rather than restating a signature: Hermes 0.21.3 added
        # an `emitter` to the quiet runner and passed it on every call, and a
        # wrapper that named exactly two parameters turned every chat turn into
        # a TypeError while cron, which does not come through here, carried on
        # working. Reported by erohtar (#1), who also found the cause.
        configure = getattr(cli, "_configure_quiet_agent", None)
        if configure:

            def configured(agent, *args, **kwargs):
                configure(agent, *args, **kwargs)
                configure_fallbacks(agent, emit)
                agent.stream_delta_callback = lambda delta: (
                    emit("delta", text=delta) if isinstance(delta, str) else None
                )

            cli._configure_quiet_agent = configured
        quiet = getattr(cli, "_run_quiet_single_query", None)
        if quiet:

            def run(instance, query, *args, **kwargs):
                # Startup diagnostics are not part of the companion's reply.
                output.seek(0)
                output.truncate(0)
                try:
                    return quiet(instance, query, *args, **kwargs)
                finally:
                    emit("session", id=instance.session_id)

            cli._run_quiet_single_query = run
        from hermes_cli.main import main as hermes_main

        try:
            hermes_main()
        except SystemExit as exc:
            code = exc.code or 0
    # Only the reply: a model that thinks out loud in <think> tags keeps its thinking.
    import re

    final = re.sub(
        r"<(think|thinking|reasoning)>[\s\S]*?(</\1>|$)",
        "",
        output.getvalue(),
        flags=re.I,
    )
    emit("final", text=final[-1000000:])
    return code


if __name__ == "__main__":
    sys.exit(main())
