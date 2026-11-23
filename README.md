# School organizer: A* vs utility-based agent

From your classes, the hours you want to spend on each subject and your fixed rules (sleep,
meals, commute, extracurriculars), the program builds your weekly schedule so you finish your
homework and projects early. It builds it in two ways and compares them:

- **Utility-based agent:** at each step it does the task with the highest utility U(t).
- **A\* search agent:** it searches for the task order with the lowest cost (finish early, no late work).

## How to run it
1. Python 3.10 or newer. Tkinter comes with Python on Windows and macOS (on Linux: `sudo apt install python3-tk`).
2. In this folder: `python gui.py`
3. To repeat the demo with a fixed date: `python gui.py "2026-11-23 07:00"`
4. Algorithm checks: `python agent.py`

## What you enter (all from the interface, saved in `data.json`)
1. **Subjects and classes:** each subject with its total weekly hours (e.g. Mathematics 10 h),
   and each class session (e.g. Mathematics Monday 09:00 to 11:00). Outside-class hours are
   total minus class (10 - 6 = 4 h).
2. **Rules:** sleep, meals, commute, extracurriculars. Days as letters M T W R F S U (R = Thursday, U = Sunday).
3. **Tasks and projects:** due date, estimated hours, weight in the grade and difficulty.
4. **Schedule:** builds the 7-day plan, lets you pick which agent to show and record unexpected events.
5. **Summary:** priorities, when each task finishes with each agent and hours per subject.

To edit a row: click it, change the fields, "Save". To add one: "New", fill the fields, "Save".

## Settings in `agent.py`
- `UTILITY_WEIGHTS`: utility weights (grade weight, urgency, difficulty).
- `LATE_PENALTY`: how much one late hour costs.
- `MAX_STUDY_PER_DAY`: maximum study hours of the same subject per day.

## Files
- `data.py`: data model and free hours. `agent.py`: utility agent, A* and plan building. `gui.py`: interface.
