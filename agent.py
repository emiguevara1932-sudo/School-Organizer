"""The two agents that build the schedule and get compared:

  - Utility-based agent: at each step places the pending task with the highest U(t).
    It decides locally and does not look at how that choice affects the other tasks.
  - A* search agent: searches for the task order with the lowest total cost.

Cost of a plan (lower is better), with p = free hours already used before the task:
    cost(t) = weight(t) * (finish_hour(t) + LATE_PENALTY * late_hours(t))
  "finish_hour" rewards finishing early; "late_hours" punishes delivering after the due date.

A* formulation:
  - State: set of tasks already placed (bitmask); it fixes the next free block p.
  - Action: place one whole pending task starting at block p.
  - g(n): sum of cost(t) of the placed tasks.
  - h(n): for each pending task, the cost it would have if it went next.
    Admissible and consistent: no task can finish earlier or be less late than that.
"""
import heapq
import time
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass

from data import ONE_HOUR, class_hours

UTILITY_WEIGHTS = (0.4, 0.5, 0.1)  # grade weight, urgency, difficulty
LATE_PENALTY = 10                  # 1 late hour costs like 10 hours of waiting
MAX_ASTAR_TASKS = 16               # at most 2^16 states
MAX_STUDY_PER_DAY = 2              # study hours of the same subject per day


@dataclass
class Plan:
    mode: str
    order: list        # tasks in the order they are done
    cost: float
    nodes: int         # expanded nodes (A*) or decisions (utility)
    ms: float
    assignment: dict   # block start -> (label, kind, subject)
    finishes: dict     # task name -> datetime it finishes (None if it does not fit)
    late_hours: dict   # task name -> hours after the due date
    study: dict        # subject -> planned hours outside class (tasks included)


def _limits(blocks, tasks):
    """Blocks that end on time for each task (infinite if it is due after the horizon)."""
    ends = [b + ONE_HOUR for b in blocks]
    if not ends:
        return [0 for _ in tasks]
    return [bisect_right(ends, t.due_dt) if t.due_dt <= ends[-1] else float("inf") for t in tasks]


def _cost(t, limit, p):
    late = max(0, t.hours - max(0, limit - p))
    return t.weight * (p + t.hours + LATE_PENALTY * late)


def utility(t, limit, p, total):
    """U(t) and urgency(t), with urgency measured from block p."""
    free = max(0, min(limit, total) - p)
    urgency = t.hours / max(1, free)
    w1, w2, w3 = UTILITY_WEIGHTS
    return w1 * t.weight + w2 * urgency + w3 * t.difficulty, urgency


def prioritize(tasks, blocks):
    """[(task, U, urgency)] from highest to lowest utility, as seen from now."""
    lim = _limits(blocks, tasks)
    rows = [(t, *utility(t, lim[j], 0, len(blocks))) for j, t in enumerate(tasks)]
    return sorted(rows, key=lambda x: -x[1])


def astar_search(blocks, tasks):
    n, lim = len(tasks), _limits(blocks, tasks)

    def h(mask, p):
        return sum(_cost(tasks[j], lim[j], p) for j in range(n) if not mask >> j & 1)

    goal = (1 << n) - 1
    frontier = [(h(0, 0), 0.0, 0, 0, ())]  # (f, g, p, mask, order)
    closed, nodes = set(), 0
    while frontier:
        _, g, p, mask, order = heapq.heappop(frontier)
        if mask == goal:
            return list(order), g, nodes
        if mask in closed:
            continue
        closed.add(mask)
        nodes += 1
        for j in range(n):
            if not mask >> j & 1:
                m2, p2 = mask | 1 << j, p + tasks[j].hours
                g2 = g + _cost(tasks[j], lim[j], p)
                heapq.heappush(frontier, (g2 + h(m2, p2), g2, p2, m2, order + (j,)))
    return [], 0.0, nodes


def utility_search(blocks, tasks):
    lim = _limits(blocks, tasks)
    pending, order, p, cost = set(range(len(tasks))), [], 0, 0.0
    while pending:
        j = max(pending, key=lambda k: utility(tasks[k], lim[k], p, len(blocks))[0])
        cost += _cost(tasks[j], lim[j], p)
        order.append(j)
        pending.remove(j)
        p += tasks[j].hours
    return order, cost, len(order)


def plan(data, blocks, mode="astar"):
    start = time.perf_counter()
    tasks = data.tasks
    if mode == "astar" and len(tasks) > MAX_ASTAR_TASKS:
        mode = "utility"  # ponytail: 2^n states; with more than 16 tasks A* gets slow
    search = astar_search if mode == "astar" else utility_search
    order, cost, nodes = search(blocks, tasks)

    assignment, finishes, late_hours = {}, {}, {}
    study = defaultdict(float)
    p = 0
    for j in order:
        t = tasks[j]
        used = blocks[p:p + t.hours]
        for b in used:
            assignment[b] = (t.name, "task", t.subject)
        study[t.subject] += len(used)
        finishes[t.name] = used[-1] + ONE_HOUR if len(used) == t.hours else None
        late_hours[t.name] = sum(1 for b in used if b + ONE_HOUR > t.due_dt) + t.hours - len(used)
        p += t.hours

    # Outside-class hours still missing per subject = weekly goal - class - tasks already placed.
    missing = {s.name: s.weekly_hours - class_hours(data, s.name) - study[s.name] for s in data.subjects}
    per_day = defaultdict(int)
    for b in blocks[p:]:
        options = [s for s, m in missing.items() if m >= 1 and per_day[(s, b.date())] < MAX_STUDY_PER_DAY]
        if not options:
            continue
        s = max(options, key=missing.get)
        assignment[b] = (f"Study {s}", "study", s)
        missing[s] -= 1
        study[s] += 1
        per_day[(s, b.date())] += 1

    ms = (time.perf_counter() - start) * 1000
    return Plan(mode, [tasks[j] for j in order], cost, nodes, ms, assignment, finishes,
                late_hours, dict(study))


if __name__ == "__main__":
    # Checks: A* matches brute force and is never worse than the utility agent;
    # a rule that crosses midnight takes the right hours.
    from datetime import datetime, timedelta
    from itertools import permutations
    from random import Random

    from data import Data, Rule, Task, free_blocks

    d = Data(rules=[Rule("Sleep", list(range(7)), "23:00", "07:00")])
    free = free_blocks(d, datetime(2026, 11, 23, 0), days=1)
    assert [b.hour for b in free] == list(range(7, 23)), free

    rnd = Random(1)
    base = datetime(2026, 11, 23, 7)
    blocks = [base + timedelta(hours=i) for i in range(30)]
    for _ in range(50):
        tasks = [Task(f"t{i}", "S", (base + timedelta(hours=rnd.randint(1, 40))).strftime("%Y-%m-%d %H:%M"),
                      rnd.randint(1, 8), rnd.choice([0.05, 0.1, 0.3]), 0.5) for i in range(5)]
        lim = _limits(blocks, tasks)

        def total(order):
            p, s = 0, 0.0
            for j in order:
                s += _cost(tasks[j], lim[j], p)
                p += tasks[j].hours
            return s

        _, c_astar, _ = astar_search(blocks, tasks)
        _, c_util, _ = utility_search(blocks, tasks)
        assert abs(c_astar - min(total(o) for o in permutations(range(5)))) < 1e-9
        assert c_astar <= c_util + 1e-9
    print("OK: A* optimal in 50 random cases, never worse than the utility agent; overnight rules correct")
