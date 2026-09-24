"""TEST DOUBLE of the quiet CLI hooks the executor wraps. Never shipped."""


def _configure_quiet_agent(agent, *args, **kwargs):
    agent.stream_delta_callback = None
