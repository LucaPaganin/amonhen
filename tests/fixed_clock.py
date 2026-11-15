"""A clock stopped on a date, for tests that must not depend on the day they run."""
import datetime as dt
from dataclasses import dataclass


@dataclass
class FixedClock:
    day: dt.date

    def today(self) -> dt.date:
        return self.day

    def now(self) -> dt.datetime:
        return dt.datetime.combine(self.day, dt.time(12, 0), tzinfo=dt.UTC)
