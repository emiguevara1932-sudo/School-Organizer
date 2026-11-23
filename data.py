"""Data model: subjects, classes, fixed rules, tasks and unexpected events (saved in data.json),
and which 1-hour blocks of the week are still free."""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
FMT = "%Y-%m-%d %H:%M"
ONE_HOUR = timedelta(hours=1)


@dataclass
class Subject:
    name: str
    weekly_hours: float  # total time you want to spend on it (class + outside class)


@dataclass
class ClassSession:
    subject: str
    day: int     # 0 = Monday
    start: str   # "HH:MM"
    end: str


@dataclass
class Rule:
    activity: str  # Sleep, Lunch, Commute, Extracurricular...
    days: list     # list of days 0-6
    start: str
    end: str       # if end <= start, it crosses midnight (e.g. sleep 23:00 to 07:00)


@dataclass
class Task:
    name: str
    subject: str
    due: str       # "YYYY-MM-DD HH:MM"
    hours: int
    weight: float  # share of the final grade (0-1)
    difficulty: float = 0.5

    @property
    def due_dt(self):
        return datetime.strptime(self.due, FMT)


@dataclass
class Event:
    start: str     # "YYYY-MM-DD HH:MM"
    end: str


@dataclass
class Data:
    subjects: list = field(default_factory=list)
    classes: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    tasks: list = field(default_factory=list)
    events: list = field(default_factory=list)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return Data()
    return Data([Subject(**x) for x in raw.get("subjects", [])],
                [ClassSession(**x) for x in raw.get("classes", [])],
                [Rule(**x) for x in raw.get("rules", [])],
                [Task(**x) for x in raw.get("tasks", [])],
                [Event(**x) for x in raw.get("events", [])])


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(data), f, ensure_ascii=False, indent=2)


def hour(text, round_up=False):
    """'07:30' -> 7 (or 8 with round_up=True). Everything works in 1-hour blocks."""
    h, m = map(int, text.split(":"))
    return h + (1 if round_up and m else 0)


def covered_hours(start, end):
    """List of (day_offset, hour) an interval takes; handles crossing midnight."""
    a, b = hour(start), hour(end, round_up=True)
    if b > a:
        return [(0, h) for h in range(a, b)]
    return [(0, h) for h in range(a, 24)] + [(1, h) for h in range(0, b)]


def class_hours(data, subject):
    return sum(len(covered_hours(c.start, c.end)) for c in data.classes if c.subject == subject)


def busy_blocks(data, since, days=7):
    """Fixed blocks of the week: {block_start: (label, kind)}. Classes win over rules."""
    base = since.replace(hour=0, minute=0, second=0, microsecond=0)
    busy = {}

    def put(b, label, kind):
        busy.setdefault(b, (label, kind))

    for d in range(-1, days + 1):  # -1 to catch what crosses midnight
        day = base + timedelta(days=d)
        for c in data.classes:
            if c.day == day.weekday():
                for extra, h in covered_hours(c.start, c.end):
                    put(day + timedelta(days=extra, hours=h), f"Class {c.subject}", "class")
    for e in data.events:
        b, end = datetime.strptime(e.start, FMT), datetime.strptime(e.end, FMT)
        while b < end:
            put(b, "Unexpected event", "event")
            b += ONE_HOUR
    for d in range(-1, days + 1):
        day = base + timedelta(days=d)
        for r in data.rules:
            if day.weekday() in r.days:
                for extra, h in covered_hours(r.start, r.end):
                    put(day + timedelta(days=extra, hours=h), r.activity, "rule")
    return busy


def week_start(since):
    b = since.replace(minute=0, second=0, microsecond=0)
    return b if b == since else b + ONE_HOUR


def free_blocks(data, since, days=7):
    """Starts of the 1-hour blocks not taken by classes, rules or events."""
    busy = busy_blocks(data, since, days)
    b = week_start(since)
    end = b + timedelta(days=days)
    free = []
    while b < end:
        if b not in busy:
            free.append(b)
        b += ONE_HOUR
    return free
