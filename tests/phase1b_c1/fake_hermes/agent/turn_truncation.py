"""TEST DOUBLE of agent/turn_truncation.py's module-level `append_message` (0e9fc2cc15 calling
convention). Protocol double only: NOT evidence about Hermes; the pinned lane is."""


def append_message(messages, message, *args, **kwargs):
    messages.append(message)
    return message
