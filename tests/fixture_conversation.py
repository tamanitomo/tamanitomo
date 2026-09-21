"""One day of real conversation, shared by the tests that measure closeness.

Closeness is scored on what a day actually contained, so a fixture of one
"hello" per day no longer stands in for two months of talking -- and should not,
since believing that it did was the fault being fixed. Anything testing the
relationship meter seeds days that look like the thing being measured.
"""
import datetime as dt

UTC = dt.timezone.utc

A_GOOD_DAY = [
    (9, "Morning. I slept badly again -- kept turning over that thing at work, "
        "and not the deadline itself so much as the fact that I said yes to it "
        "without thinking about whether I had the room for it."),
    (9, "I think that is the part that actually bothers me. I do it every time."),
    (10, "Going to try to get the first half of it drafted before lunch and see "
         "whether it is as bad as it feels at seven in the morning."),
    (13, "It was not as bad as it felt. Two hours and most of the structure is "
         "there. Lunch at that place by the river we talked about last week."),
    (13, "I sat outside afterwards for twenty minutes and did not look at my "
         "phone once, which I am counting as an achievement."),
    (17, "My sister called. She asked me straight out whether I was happy and I "
         "did not have an answer ready, which I have been chewing on since."),
    (20, "Home. I keep coming back to the fact that I could not answer her. Not "
         "because the answer is no -- more that I have not checked in a while."),
    (20, "I think I am going to say no to the next one that comes in and see "
         "what actually happens. Probably nothing. That is rather the point."),
    (21, "Thank you for listening to all of that. It helped to say it out loud "
         "to someone who was going to remember it tomorrow."),
    (22, "Going to read for a bit and actually go to bed at a sensible hour for "
         "once. Remind me tomorrow that I said the thing about saying no."),
]


def a_days_conversation(day):
    """One full-value day of messages, as (timestamp, text) pairs."""
    return [(dt.datetime.combine(day, dt.time(hour, (n * 11) % 60), UTC), text)
            for n, (hour, text) in enumerate(A_GOOD_DAY)]
