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


def hour_budget(data):
    """Hours outside class per subject, with the rule "tasks replace study hours".

    study goal = weekly hours - class hours            (Mathematics: 10 - 6 = 4 h)
    If the subject has tasks or projects, their hours use the study goal first:
        study (topics) = max(0, goal - task hours)     (project 6 h -> 0 h of plain study)
        extra          = max(0, task hours - goal)     (project 6 h -> 2 h extra this week)
    So outside class you spend max(goal, task hours), never goal + task hours.
    """
    out = {}
    for s in data.subjects:
        in_class = class_hours(data, s.name)
        goal = max(0, s.weekly_hours - in_class)
        tasks = sum(t.hours for t in data.tasks if t.subject == s.name)
        out[s.name] = {"total": s.weekly_hours, "class": in_class, "goal": goal, "tasks": tasks,
                       "study": max(0, goal - tasks), "extra": max(0, tasks - goal)}
    return out


def overlaps(data):
    """Checks the class timetable against the fixed rules (sleep, meals, commute...).

    Returns readable warnings such as "Class Mathematics (Monday 08:00) overlaps Commute",
    and the same for two classes at the same time.
    The program still works (classes win), but the student probably typed something wrong."""
    def week_hours(day, start, end):  # (weekday, hour) pairs, wrapping Sunday -> Monday
        return {((day + extra) % 7, h) for extra, h in covered_hours(start, end)}

    rules = {}
    for r in data.rules:
        for d in r.days:
            for slot in week_hours(d, r.start, r.end):
                rules.setdefault(slot, r.activity)
    out, taken = [], {}  # taken: (weekday, hour) -> index of the class there
    for i, c in enumerate(data.classes):
        hit_rule = hit_class = None
        for d, h in sorted(week_hours(c.day, c.start, c.end)):
            if (d, h) in rules and not hit_rule:
                hit_rule = f"Class {c.subject} ({DAYS[d]} {h:02d}:00) overlaps {rules[(d, h)]}"
            j = taken.setdefault((d, h), i)
            if j != i and not hit_class:
                hit_class = f"Class {c.subject} ({DAYS[d]} {h:02d}:00) overlaps class {data.classes[j].subject}"
        out += [x for x in (hit_rule, hit_class) if x]
    return out


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
