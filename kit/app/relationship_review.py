"""Profile-scoped inspection and explicit review of relationship restrictions."""

from fastapi import HTTPException


def register(app, load):
    @app.get("/api/relationship/review")
    def relationship_review_report():
        import companion_relationship_review as review

        return review.report(load())

    @app.post("/api/relationship/review")
    def relationship_review_record(payload: dict):
        import companion_relationship_review as review

        revision, reason = payload.get("revision"), payload.get("reason")
        if not isinstance(revision, str) or not revision.strip():
            raise HTTPException(400, "Load the current boundary review first")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise HTTPException(400, "Explain this review in 1–1,000 characters")
        try:
            return review.review(load(), revision=revision, reason=reason)
        except review.StaleReviewError as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
