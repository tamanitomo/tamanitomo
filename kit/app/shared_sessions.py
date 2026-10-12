"""Profile-scoped shared experiences. Opening the page never contacts a provider."""

import companion_music as music
import companion_viewing as viewing


def register(app, load):
    @app.get("/api/viewing/sessions")
    def sessions():
        return viewing.snapshot(load())

    @app.post("/api/viewing/sessions")
    def start(payload: dict):
        c = load()
        result = viewing.together(
            c,
            payload.get("title", ""),
            payload.get("hours", 3),
            mode=payload.get("mode", "auto"),
            comments=payload.get("comments", "occasional"),
            evidence="Started together in the workspace by the human.",
        )
        if not result.get("written"):
            raise ValueError(
                result.get("reason") or "There is already a shared session"
            )
        return viewing.snapshot(c)

    @app.post("/api/viewing/sessions/{ident}/{action}")
    def change(ident: str, action: str, payload: dict):
        c = load()
        if action in ("pause", "resume", "stop"):
            getattr(viewing, action)(c, session_id=ident)
        elif action in ("report", "moment"):
            text = payload.get("text", "")
            limit = 400 if action == "report" else 350
            if not isinstance(text, str) or not text.strip() or len(text) > limit:
                raise ValueError(
                    f"Use 1–{limit} characters for a shared moment or checkpoint"
                )
            # The human's own submission is the evidence, not an invented quote.
            evidence = f"The human wrote in the workspace: {text}"
            if action == "report":
                viewing.report(
                    c,
                    text,
                    evidence,
                    session_id=ident,
                    position_min=payload.get("position_min"),
                )
            else:
                viewing.moment(c, text, evidence, session_id=ident)
        else:
            raise ValueError("Unknown shared-session action")
        return viewing.snapshot(c)

    @app.get("/api/music/suggestions")
    def suggestions():
        c = load()
        return {"suggestions": music.history(c), "enabled": music.enabled(c)}
