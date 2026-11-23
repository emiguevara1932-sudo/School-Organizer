# School organizer: utility-based agent + A* search

From your classes, the hours you want to spend on each subject and your fixed rules (sleep,
meals, commute, extracurriculars), the program builds your weekly schedule hour by hour so you
finish your homework and projects early. Two AI topics work together in one planner:

1. **Utility-based agent (what matters):** rates every task with
   `U = 0.4 weight + 0.5 urgency + 0.1 difficulty` (urgency = hours / free hours before the due date)
   and turns that into a cost: `cost = U x (hour it finishes + 10 x late hours)`.
2. **A\* search (in which order):** finds the order of tasks with the lowest total cost.
   Its heuristic is admissible, so the order is the best one.
3. The free hours left become study time per subject. The agent re-plans after every change.

## How to run it
1. Python 3.10 or newer. Tkinter comes with Python on Windows and macOS (on Linux: `sudo apt install python3-tk`).
2. In this folder: `python gui.py`
3. To repeat the demo with a fixed date: `python gui.py "2026-11-23 07:00"`
4. Checks (A* optimal, hour rule, overnight rules, overlaps): `python agent.py`

## What you enter (all from the interface, saved in `data.json`)
1. **Subjects and classes:** each subject with its total weekly hours, and each class session.
   The table shows class hours and the study goal: Mathematics 10 h with 3 classes of 2 h
   = 6 h of class + a study goal of 4 h.
2. **Rules:** sleep, meals, commute, extracurriculars. Days as letters M T W R F S U
   (R = Thursday, U = Sunday). If the end is before the start it crosses midnight (sleep 23:00 to 07:00).
3. **Tasks and projects:** due date, estimated hours, weight in the grade and difficulty.
4. **Schedule:** the 7-day plan. "Something came up" records an event and re-plans.
5. **How the plan was made:** step 1 the utility of each task, step 2 the order A* chose,
   step 3 the hours per subject.

### Hour rule (tasks replace study hours)
Tasks of a subject use its study goal first. A 6 h Mathematics project with a 4 h goal means
0 h of plain study + 2 h extra (6 h outside class, not 4 + 6). A 3 h project means 3 h + 1 h of study.

### Checks on what you type
Times must be HH:MM; a class must end after it starts on the same day; a rule cannot start and
end at the same time. The Schedule tab warns if a class overlaps a rule or another class, or if
there are not enough free hours. Deleting a subject also deletes its classes and tasks.

To edit a row: click it, change the fields, "Save". To add one: "New", fill the fields, "Save".

## Settings in `agent.py`
- `UTILITY_WEIGHTS`: utility weights (grade weight, urgency, difficulty).
- `LATE_PENALTY`: how much one late hour costs.
- `MAX_ASTAR_TASKS`: above this many tasks the agent orders by utility only (A* has 2^n states).
- `MAX_STUDY_PER_DAY`: maximum study hours of the same subject per day.

## Files
- `data.py`: data model, free hours, hour rule (`hour_budget`) and overlap check.
- `agent.py`: utility-based agent, A* search and the plan that joins them.
- `gui.py`: interface.
