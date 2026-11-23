"""The planner: a utility-based agent that uses A* search to decide.

The two course topics are not competitors here, each one does a different job:

  1. UTILITY-BASED AGENT (topic 02, agents and environments) decides WHAT MATTERS.
     It perceives the data (tasks, due dates, free hours) and gives every task a utility
         U(t) = 0.4 * weight(t) + 0.5 * urgency(t) + 0.1 * difficulty(t)
         urgency(t) = hours(t) / free hours left before its due date
     A plan is good when the tasks with high U finish early and nothing is late, so the
     agent turns its utility into a cost to minimise (lower cost = higher utility):
         cost(t) = U(t) * (finish_hour(t) + LATE_PENALTY * late_hours(t))
     finish_hour(t) is counted in free hours from now (p + hours(t)).

  2. A* SEARCH (topic 03, problem solving by search) decides HOW: in which order.
     The agent cannot try every order by hand (6 tasks = 720 orders, 10 = 3.6 million), so
     it asks A* for the order with the lowest total cost:
       - State: set of tasks already placed (bitmask); it fixes the next free hour p.
       - Action: place one whole pending task starting at free hour p.
       - g(n): cost of the tasks already placed.
       - h(n): for each pending task, the cost it would have if it went next.
         Admissible and consistent: a task can never finish earlier or be less late
         than if it went next, so A* returns the best order (checked in __main__).

  After A*, the agent fills the free hours left with study blocks (see data.hour_budget)
  and re-plans every time the data changes (that is the agent loop in gui.py).
"""
import heapq
import time
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass

from data import ONE_HOUR, hour_budget

UTILITY_WEIGHTS = (0.4, 0.5, 0.1)  # grade weight, urgency, difficulty
LATE_PENALTY = 10                  # 1 late hour costs like 10 hours of waiting
MAX_ASTAR_TASKS = 16               # at most 2^16 states
MAX_STUDY_PER_DAY = 2              # study hours of the same subject per day


@dataclass
class Plan:
    utilities: list    # [(task, U, urgency)] from the utility-based agent, highest U first
    order: list        # tasks in the order A* chose
    cost: float        # total cost of that order (lower = more utility)
    nodes: int         # states A* expanded
    states: int        # 2^n possible states
    searched: bool     # False if there were too many tasks and the utility ranking was used
    ms: float
    assignment: dict   # block start -> (label, kind, subject)
    starts: dict       # task name -> datetime it starts
    finishes: dict     # task name -> datetime it finishes (None if it does not fit)
    late_hours: dict   # task name -> hours after the due date
    costs: dict        # task name -> cost(t)
    budget: dict       # subject -> hour_budget row, plus "planned" study hours


# ---------- 1. Utility-based agent: what each task is worth ----------

def _limits(blocks, tasks):
    """For each task, how many free blocks end before its due date (inf if due after the week)."""
    ends = [b + ONE_HOUR for b in blocks]
    if not ends:
        return [0 for _ in tasks]
    return [bisect_right(ends, t.due_dt) if t.due_dt <= ends[-1] else float("inf") for t in tasks]


def utility(t, limit, total):
    """U(t) and urgency(t), seen from now. Urgency > 1 means there is no longer enough time."""
    urgency = t.hours / max(1, min(limit, total))
    w1, w2, w3 = UTILITY_WEIGHTS
    return w1 * t.weight + w2 * urgency + w3 * t.difficulty, urgency


def evaluate(tasks, blocks):
    """The agent's evaluation: [(task, U, urgency)] from highest to lowest utility."""
    lim = _limits(blocks, tasks)
    rows = [(t, *utility(t, lim[j], len(blocks))) for j, t in enumerate(tasks)]
    return sorted(rows, key=lambda x: -x[1])


def task_cost(u, hours, limit, p):
    """Cost of doing a task of utility u starting at free hour p (the utility turned into a cost)."""
    late = max(0, hours - max(0, limit - p))
    return u * (p + hours + LATE_PENALTY * late)


# ---------- 2. A* search: the order with the lowest cost ----------

def astar(hours, limits, u):
    """A* over task orders. hours, limits and u are lists with one entry per task.
    Returns (order, cost, expanded nodes)."""
    n = len(hours)

    def h(mask, p):  # every pending task as if it went next: a lower bound of what is left
        return sum(task_cost(u[j], hours[j], limits[j], p) for j in range(n) if not mask >> j & 1)

    goal = (1 << n) - 1
    frontier = [(h(0, 0), 0.0, 0, 0, ())]  # (f = g + h, g, p, mask, order)
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
                m2, p2 = mask | 1 << j, p + hours[j]
                g2 = g + task_cost(u[j], hours[j], limits[j], p)
                heapq.heappush(frontier, (g2 + h(m2, p2), g2, p2, m2, order + (j,)))
    return [], 0.0, nodes


# ---------- the agent puts both together ----------

def plan(data, blocks):
    """Perceive -> evaluate with utility -> search with A* -> act (fill the week)."""
    start = time.perf_counter()
    tasks = data.tasks
    lim = _limits(blocks, tasks)
    u = [utility(t, lim[j], len(blocks))[0] for j, t in enumerate(tasks)]
    hours = [t.hours for t in tasks]

    searched = len(tasks) <= MAX_ASTAR_TASKS
    if searched:
        order, cost, nodes = astar(hours, lim, u)
    else:
        # ponytail: 2^n states; above 16 tasks the agent just follows its utility ranking
        order, nodes = sorted(range(len(tasks)), key=lambda j: -u[j]), 0
        cost = 0.0

    assignment, starts, finishes, late_hours, costs = {}, {}, {}, {}, {}
    p = 0
    for j in order:
        t = tasks[j]
        used = blocks[p:p + t.hours]
        for b in used:
            assignment[b] = (t.name, "task", t.subject)
        starts[t.name] = used[0] if used else None
        finishes[t.name] = used[-1] + ONE_HOUR if len(used) == t.hours else None
        late_hours[t.name] = sum(1 for b in used if b + ONE_HOUR > t.due_dt) + t.hours - len(used)
        costs[t.name] = task_cost(u[j], t.hours, lim[j], p)
        p += t.hours
    if not searched:
        cost = sum(costs.values())

    # Study blocks: the hours each subject still needs after its tasks (data.hour_budget).
    budget = hour_budget(data)
    missing = {s: row["study"] for s, row in budget.items()}
    for row in budget.values():
        row["planned"] = 0
    per_day = defaultdict(int)
    for b in blocks[p:]:
        options = [s for s, m in missing.items() if m >= 1 and per_day[(s, b.date())] < MAX_STUDY_PER_DAY]
        if not options:
            continue
        s = max(options, key=missing.get)  # the subject that still needs the most hours
        assignment[b] = (f"Study {s}", "study", s)
        missing[s] -= 1
        budget[s]["planned"] += 1
        per_day[(s, b.date())] += 1

    ms = (time.perf_counter() - start) * 1000
    return Plan(evaluate(tasks, blocks), [tasks[j] for j in order], cost, nodes, 2 ** len(tasks),
                searched, ms, assignment, starts, finishes, late_hours, costs, budget)


if __name__ == "__main__":
    # Checks: A* finds the best order (brute force), the hour rule, overnight rules, overlaps.
    from datetime import datetime
    from itertools import permutations
    from random import Random

    from data import ClassSession, Data, Rule, Subject, Task, free_blocks, overlaps

    # A* returns the lowest-cost order in 50 random cases.
    rnd = Random(1)
    for _ in range(50):
        hours = [rnd.randint(1, 8) for _ in range(5)]
        limits = [rnd.choice([rnd.randint(1, 30), float("inf")]) for _ in range(5)]
        u = [rnd.uniform(0.05, 1.5) for _ in range(5)]

        def total(order):
            p, s = 0, 0.0
            for j in order:
                s += task_cost(u[j], hours[j], limits[j], p)
                p += hours[j]
            return s

        _, c, _ = astar(hours, limits, u)
        assert abs(c - min(total(o) for o in permutations(range(5)))) < 1e-9

    # Hour rule: Mathematics 10 h, 3 classes of 2 h -> goal 4 h.
    math = Data(subjects=[Subject("Mathematics", 10)],
                classes=[ClassSession("Mathematics", d, "09:00", "11:00") for d in (0, 2, 4)])
    assert hour_budget(math)["Mathematics"] == {"total": 10, "class": 6, "goal": 4, "tasks": 0,
                                                "study": 4, "extra": 0}
    math.tasks = [Task("Final project", "Mathematics", "2026-12-04 23:59", 6, 0.3)]
    b = hour_budget(math)["Mathematics"]
    assert (b["study"], b["extra"]) == (0, 2), b       # 6 h project = 4 h of the goal + 2 h extra
    math.tasks[0].hours = 3
    b = hour_budget(math)["Mathematics"]
    assert (b["study"], b["extra"]) == (1, 0), b       # 3 h project + 1 h of plain study

    # A rule that crosses midnight takes the right hours.
    d = Data(rules=[Rule("Sleep", list(range(7)), "23:00", "07:00")])
    free = free_blocks(d, datetime(2026, 11, 23, 0), days=1)
    assert [b.hour for b in free] == list(range(7, 23)), free

    # A class at the same time as a rule is reported.
    d.classes = [ClassSession("Mathematics", 0, "06:00", "08:00")]
    assert overlaps(d) == ["Class Mathematics (Monday 06:00) overlaps Sleep"], overlaps(d)
    d.classes.append(ClassSession("Physics", 0, "07:00", "09:00"))
    assert overlaps(d)[-1] == "Class Physics (Monday 07:00) overlaps class Mathematics", overlaps(d)
    print("OK: A* optimal in 50 random cases; hour rule; overnight rules; class/rule overlaps")
