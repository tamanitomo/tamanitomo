

def test_summary_puts_earlier_categories_before_other(tmp_path):
    import datetime as dt
    import companion_self as s
    from types import SimpleNamespace

    now = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone.utc)
    root = tmp_path / "human"
    root.mkdir()
    s.record_fact(root, "Likes tea.", "said so", now, category="other")
    s.record_fact(
        root, "Lives in Ohio.", "said so", now + dt.timedelta(minutes=1),
        category=s.CATEGORIES[0],
    )
    c = SimpleNamespace(
        human_dir=root,
        life=tmp_path / "life",
        budgets=lambda: {"facts": 10_000, "preferences": 100, "questions": 100},
    )
    text = s.summary(c)["human_profile"]
    assert text.index("Lives in Ohio.") < text.index("Likes tea.")
