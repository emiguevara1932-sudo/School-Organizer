"""Organizer user interface. Usage: python gui.py ["YYYY-MM-DD HH:MM"]
The optional date fixes "now" (useful to repeat the scenarios in the report).

Agent loop: the input tabs are the agent's sensors; every change calls App.changed(),
which saves the data and re-plans with agent.plan() (utility-based agent + A* search).
The Schedule and "How the plan was made" tabs are its actuators: they show the plan and why."""
import os
import sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, simpledialog, ttk

import agent
import data as dm

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
LETTERS = "MTWRFSU"  # Monday ... Sunday (R = Thursday, U = Sunday)
COLORS = {"class": "#9ec5fe", "task": "#ffc078", "study": "#8ce99a", "rule": "#dee2e6",
          "event": "#ff8787", "past": "#f8f9fa", "": "#ffffff"}


def days_to_text(days):
    return "".join(LETTERS[d] for d in sorted(days))


def text_to_days(text):
    days = sorted({LETTERS.index(c) for c in text.upper() if c in LETTERS})
    if not days:
        raise ValueError("Write the days with the letters M T W R F S U, for example MTWRF")
    return days


def check_time(text):
    try:
        h, m = map(int, text.split(":"))
    except ValueError:
        raise ValueError(f"'{text}' is not a time. Use HH:MM, for example 09:00") from None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"'{text}' is not a valid time (00:00 to 23:59).")
    return f"{h:02d}:{m:02d}"


def number(text, what):
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{what} must be a number.") from None


class Section(ttk.LabelFrame):
    """Table + form to add, edit (select and Save) or delete rows."""

    def __init__(self, parent, title, fields, rows, create, delete, on_change, extra=()):
        """extra: read-only columns the program computes (shown after the fields)."""
        super().__init__(parent, text=title, padding=6)
        self.rows, self.create, self.delete, self.on_change = rows, create, delete, on_change
        names = [f[0] for f in fields] + list(extra)
        self.table = ttk.Treeview(self, columns=names, show="headings", height=7)
        for n in names:
            self.table.heading(n, text=n)
            self.table.column(n, width=140, anchor="w")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self._select)
        form = ttk.Frame(self)
        form.pack(fill="x", pady=4)
        self.entries = []
        for i, (name, options) in enumerate(fields):
            ttk.Label(form, text=name).grid(row=0, column=i, sticky="w")
            e = ttk.Combobox(form, values=options, width=16) if options is not None else ttk.Entry(form, width=18)
            e.grid(row=1, column=i, padx=2)
            self.entries.append(e)
        buttons = ttk.Frame(self)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="New", command=self._new).pack(side="left")
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left", padx=6)
        ttk.Button(buttons, text="Delete selected", command=self._delete).pack(side="left", padx=6)
        self.refresh()

    def refresh(self):
        self.table.delete(*self.table.get_children())
        for i, row in enumerate(self.rows()):
            self.table.insert("", "end", iid=str(i), values=row)

    def _select(self, _):
        sel = self.table.selection()
        if sel:
            for e, v in zip(self.entries, self.table.item(sel[0], "values")):
                e.delete(0, "end")
                e.insert(0, v)

    def _new(self):
        self.table.selection_remove(*self.table.selection())
        for e in self.entries:
            e.delete(0, "end")

    def _save(self):
        sel = self.table.selection()
        try:
            self.create([e.get().strip() for e in self.entries], int(sel[0]) if sel else None)
        except (ValueError, KeyError) as error:
            messagebox.showerror("Invalid data", str(error) or "Check the fields.")
            return
        self.on_change()

    def _delete(self):
        sel = self.table.selection()
        if sel:
            self.delete(int(sel[0]))
            self.on_change()


def replace(items, index, new):
    if index is None:
        items.append(new)
    else:
        items[index] = new


class App(tk.Tk):
    def __init__(self, now=None):
        super().__init__()
        self.title("School organizer: utility-based agent + A* search")
        self.geometry("1180x800")
        self.d = dm.load(PATH)
        self.now = tk.StringVar(value=(now or datetime.now()).strftime(dm.FMT))
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.sections = []
        self._tab_subjects()
        self._tab_rules()
        self._tab_tasks()
        self._tab_schedule()
        self._tab_summary()
        self.changed()

    # ---------- input tabs ----------
    def _subject_names(self):
        return [s.name for s in self.d.subjects]

    def _tab_subjects(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="1. Subjects and classes")
        d = self.d

        def create_subject(v, i):
            if not v[0]:
                raise ValueError("The subject needs a name.")
            if v[0] in self._subject_names() and (i is None or d.subjects[i].name != v[0]):
                raise ValueError("That subject already exists.")
            hours = number(v[1], "Weekly hours")
            if hours <= 0:
                raise ValueError("Weekly hours must be more than 0.")
            if i is not None and d.subjects[i].name != v[0]:  # renamed: keep its classes and tasks
                for x in d.classes + d.tasks:
                    if x.subject == d.subjects[i].name:
                        x.subject = v[0]
            replace(d.subjects, i, dm.Subject(v[0], hours))

        def delete_subject(i):  # its classes and tasks go with it
            name = d.subjects.pop(i).name
            d.classes[:] = [c for c in d.classes if c.subject != name]
            d.tasks[:] = [t for t in d.tasks if t.subject != name]

        def create_class(v, i):
            if v[0] not in self._subject_names():
                raise ValueError("Add the subject above first.")
            if v[1] not in dm.DAYS:
                raise ValueError("Pick the day from the list.")
            start, end = check_time(v[2]), check_time(v[3])
            if end <= start:
                raise ValueError("A class must end after it starts, on the same day.")
            replace(d.classes, i, dm.ClassSession(v[0], dm.DAYS.index(v[1]), start, end))

        ttk.Label(tab, justify="left", text=(
            "Weekly hours = all the time for the subject (class + outside class). Example: Mathematics 10 h "
            "with 3 classes of 2 h = 6 h of class + a study goal of 4 h.\n"
            "Tasks and projects of a subject use its study goal first: a 6 h Mathematics project takes "
            "those 4 h plus 2 h extra, not 4 + 6.")).pack(anchor="w")
        subjects = Section(
            tab, "Subjects", [("Subject", None), ("Weekly hours", None)],
            lambda: [(s.name, s.weekly_hours, b["class"], b["goal"])
                     for s, b in ((s, dm.hour_budget(d)[s.name]) for s in d.subjects)],
            create_subject, delete_subject, self.changed,
            extra=("Class hours (from the classes below)", "Study goal = weekly - class"))
        classes = Section(
            tab, "Classes (one row per session)",
            [("Subject", self._subject_names()), ("Day", dm.DAYS), ("Start (HH:MM)", None), ("End (HH:MM)", None)],
            lambda: [(c.subject, dm.DAYS[c.day], c.start, c.end) for c in d.classes],
            create_class, lambda i: d.classes.pop(i), self.changed)
        subjects.pack(fill="both", expand=True)
        classes.pack(fill="both", expand=True, pady=6)
        self.class_subject_box = classes.entries[0]
        self.sections += [subjects, classes]

    def _tab_rules(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="2. Rules (sleep, meals...)")
        d = self.d

        def create(v, i):
            if not v[0]:
                raise ValueError("Write the activity.")
            start, end = check_time(v[2]), check_time(v[3])
            if start == end:
                raise ValueError("Start and end are the same time.")
            replace(d.rules, i, dm.Rule(v[0], text_to_days(v[1]), start, end))

        ttk.Label(tab, text="Days as letters: M T W R F S U (R = Thursday, U = Sunday). "
                            "If the end is before the start, it crosses midnight (sleep 23:00 to 07:00).").pack(anchor="w")
        s = Section(tab, "Fixed rules",
                    [("Activity", ["Sleep", "Breakfast", "Lunch", "Dinner", "Commute", "Extracurricular"]),
                     ("Days", None), ("Start (HH:MM)", None), ("End (HH:MM)", None)],
                    lambda: [(r.activity, days_to_text(r.days), r.start, r.end) for r in d.rules],
                    create, lambda i: d.rules.pop(i), self.changed)
        s.pack(fill="both", expand=True)
        self.sections.append(s)

    def _tab_tasks(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="3. Tasks and projects")
        d = self.d

        def create(v, i):
            if not v[0] or v[1] not in self._subject_names():
                raise ValueError("The task needs a name and an existing subject.")
            try:
                hours = int(v[3])
            except ValueError:
                raise ValueError("Estimated hours must be a whole number.") from None
            t = dm.Task(v[0], v[1], v[2], hours, number(v[4], "Weight"), number(v[5] or 0.5, "Difficulty"))
            try:
                t.due_dt
            except ValueError:
                raise ValueError("Write the due date as YYYY-MM-DD HH:MM") from None
            if t.hours <= 0 or not 0 <= t.weight <= 1 or not 0 <= t.difficulty <= 1:
                raise ValueError("Hours > 0; weight and difficulty between 0 and 1.")
            replace(d.tasks, i, t)

        s = Section(tab, "Homework, labs and projects",
                    [("Task", None), ("Subject", self._subject_names()), ("Due (YYYY-MM-DD HH:MM)", None),
                     ("Estimated hours", None), ("Weight (0-1)", None), ("Difficulty (0-1)", None)],
                    lambda: [(t.name, t.subject, t.due, t.hours, t.weight, t.difficulty) for t in d.tasks],
                    create, lambda i: d.tasks.pop(i), self.changed)
        s.pack(fill="both", expand=True)
        self.task_subject_box = s.entries[1]
        self.sections.append(s)

    # ---------- schedule ----------
    def _tab_schedule(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="4. Schedule")
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        ttk.Label(bar, text="Plan from:").pack(side="left")
        ttk.Entry(bar, textvariable=self.now, width=17).pack(side="left", padx=4)
        ttk.Button(bar, text="Build schedule", command=self.replan).pack(side="left", padx=8)
        ttk.Button(bar, text="Something came up", command=self.add_event).pack(side="right")
        self.stats = ttk.Label(tab, font=("TkDefaultFont", 10, "bold"))
        self.stats.pack(anchor="w", pady=4)
        self.warning = ttk.Label(tab, foreground="red")
        self.warning.pack(anchor="w")
        legend = ttk.Frame(tab)
        legend.pack(anchor="w")
        for kind, text in (("class", "Class"), ("task", "Task/project"), ("study", "Study outside class"),
                           ("rule", "Fixed rule"), ("event", "Unexpected event")):
            tk.Label(legend, text=text, bg=COLORS[kind], padx=6).pack(side="left", padx=2)
        self.canvas = tk.Canvas(tab, bg="white", height=600)
        self.canvas.pack(fill="both", expand=True, pady=4)

    def _draw(self, since, busy):
        c = self.canvas
        c.delete("all")
        x0, y0, width, height = 48, 22, 155, 24
        day0 = since.replace(hour=0, minute=0)
        for d in range(7):
            day = day0 + timedelta(days=d)
            c.create_text(x0 + d * width + width / 2, 10, text=f"{dm.DAYS[day.weekday()]} {day.day}",
                          font=("TkDefaultFont", 9, "bold"))
        for h in range(24):
            c.create_text(x0 - 6, y0 + h * height + height / 2, text=f"{h:02d}:00", anchor="e",
                          font=("TkDefaultFont", 8))
            for d in range(7):
                b = day0 + timedelta(days=d, hours=h)
                if b < dm.week_start(since):
                    label, kind = "", "past"
                elif b in busy:
                    label, kind = busy[b]
                else:
                    label, kind, _ = self.plan.assignment.get(b, ("", "", ""))
                x, y = x0 + d * width, y0 + h * height
                c.create_rectangle(x, y, x + width, y + height, fill=COLORS[kind], outline="#ced4da")
                c.create_text(x + 4, y + height / 2, text=label[:24], anchor="w", font=("TkDefaultFont", 8))
        c.configure(scrollregion=c.bbox("all"))

    # ---------- how the plan was made ----------
    def _tab_summary(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="5. How the plan was made")

        def table(title, cols, widths):
            ttk.Label(tab, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(8, 0))
            t = ttk.Treeview(tab, columns=cols, show="headings", height=7)
            for col, w in zip(cols, widths):
                t.heading(col, text=col)
                t.column(col, width=w, anchor="w")
            t.pack(fill="x")
            return t

        ttk.Label(tab, justify="left", wraplength=1150, text=(
            "Step 1. The utility-based agent rates each task: U = 0.4 weight + 0.5 urgency + 0.1 difficulty "
            "(urgency = hours / free hours before the due date).\n"
            "Step 2. A* searches the order of tasks with the lowest cost, where "
            "cost = U x (hour it finishes + 10 x late hours). High-U tasks want to go early, "
            "but A* only moves them ahead if no other deadline is missed.\n"
            "Step 3. The free hours left become study time, after tasks use up each subject's study goal.")
        ).pack(anchor="w")
        self.t_utility = table("Step 1 · Utility-based agent: what each task is worth (highest U first)",
                               ("Task", "Subject", "Due", "Hours", "Weight", "Urgency", "Difficulty", "U"),
                               (180, 160, 130, 60, 70, 80, 80, 70))
        self.t_utility.tag_configure("risk", foreground="red")
        self.t_order = table("Step 2 · A* search: the order chosen and when each task is done",
                             ("Order", "Task", "U", "Starts", "Finishes", "Due", "Late hours", "Cost"),
                             (60, 180, 60, 130, 130, 130, 80, 70))
        self.t_order.tag_configure("late", foreground="red")
        self.t_subjects = table("Step 3 · Hours per subject: tasks first use the study goal, then extra hours",
                                ("Subject", "Weekly total", "Class", "Study goal", "Tasks/projects",
                                 "Study (topics)", "Extra hours", "Study placed"),
                                (170, 90, 60, 80, 100, 100, 90, 100))

    def _fill_summary(self):
        for t in (self.t_utility, self.t_order, self.t_subjects):
            t.delete(*t.get_children())
        p = self.plan
        when = lambda x: f"{dm.DAYS[x.weekday()][:3]} {x:%d %H:%M}" if x else "does not fit"
        u_of = {}
        for t, u, urg in p.utilities:
            u_of[t.name] = u
            self.t_utility.insert("", "end", tags=("risk",) if urg > 1 else (), values=(
                t.name + ("  (not enough time)" if urg > 1 else ""), t.subject, t.due, t.hours,
                t.weight, f"{urg:.2f}", t.difficulty, f"{u:.3f}"))
        for k, t in enumerate(p.order, 1):
            late = p.late_hours[t.name]
            self.t_order.insert("", "end", tags=("late",) if late else (), values=(
                k, t.name, f"{u_of[t.name]:.3f}", when(p.starts[t.name]), when(p.finishes[t.name]),
                t.due, late, f"{p.costs[t.name]:.2f}"))
        for s, row in p.budget.items():
            self.t_subjects.insert("", "end", values=(
                s, row["total"], row["class"], row["goal"], row["tasks"], row["study"], row["extra"],
                row["planned"]))

    # ---------- agent loop ----------
    def changed(self):
        """Sensor: every change to the data is saved and triggers a new plan."""
        dm.save(PATH, self.d)
        for s in self.sections:
            s.refresh()
        self.class_subject_box["values"] = self.task_subject_box["values"] = self._subject_names()
        self.replan()

    def replan(self):
        try:
            since = datetime.strptime(self.now.get(), dm.FMT)
        except ValueError:
            messagebox.showerror("Invalid date", "Use the format YYYY-MM-DD HH:MM")
            return
        blocks = dm.free_blocks(self.d, since)
        self.plan = p = agent.plan(self.d, blocks)
        search = (f"A* expanded {p.nodes} of {p.states} states" if p.searched else
                  f"more than {agent.MAX_ASTAR_TASKS} tasks: order by utility only")
        self.stats.config(text=(
            f"{len(p.order)} tasks  |  {sum(p.late_hours.values())} h late  |  cost {p.cost:.2f}  |  "
            f"{search} in {p.ms:.1f} ms  |  {len(blocks)} free hours in 7 days"))
        # Outside class you need max(study goal, task hours) per subject (data.hour_budget).
        needed = sum(max(r["goal"], r["tasks"]) for r in dm.hour_budget(self.d).values())
        notes = dm.overlaps(self.d)
        if needed > len(blocks):
            notes.insert(0, f"You need {needed:.0f} h outside class but only have {len(blocks)} free hours.")
        self.warning.config(text="Warning: " + "  ·  ".join(notes[:3]) if notes else "")
        self._draw(since, dm.busy_blocks(self.d, since))
        self._fill_summary()

    def add_event(self):
        text = simpledialog.askstring(
            "Unexpected event", "Date and hours you lose (start and end), for example:\n2026-11-26 16 20", parent=self)
        if not text:
            return
        try:
            date, h1, h2 = text.split()
            day = datetime.strptime(date, "%Y-%m-%d")
            start, end = day.replace(hour=int(h1)), day.replace(hour=int(h2))
            if end <= start:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid format", "Use: YYYY-MM-DD start_hour end_hour")
            return
        self.d.events.append(dm.Event(start.strftime(dm.FMT), end.strftime(dm.FMT)))
        self.changed()


if __name__ == "__main__":
    App(datetime.strptime(sys.argv[1], dm.FMT) if len(sys.argv) > 1 else None).mainloop()
