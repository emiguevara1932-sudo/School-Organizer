"""Organizer user interface. Usage: python gui.py ["YYYY-MM-DD HH:MM"]
The optional date fixes "now" (useful to repeat the scenarios in the report)."""
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
    dm.hour(text)  # raises ValueError if it is not HH:MM
    return text


class Section(ttk.LabelFrame):
    """Table + form to add, edit (select and Save) or delete rows."""

    def __init__(self, parent, title, fields, rows, create, delete, on_change):
        super().__init__(parent, text=title, padding=6)
        self.rows, self.create, self.delete, self.on_change = rows, create, delete, on_change
        names = [f[0] for f in fields]
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
        self.title("School organizer: A* vs utility-based agent")
        self.geometry("1180x800")
        self.d = dm.load(PATH)
        self.now = tk.StringVar(value=(now or datetime.now()).strftime(dm.FMT))
        self.mode = tk.StringVar(value="astar")
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
            replace(d.subjects, i, dm.Subject(v[0], float(v[1])))

        def create_class(v, i):
            if v[0] not in self._subject_names():
                raise ValueError("Add the subject above first.")
            replace(d.classes, i, dm.ClassSession(v[0], dm.DAYS.index(v[1]), check_time(v[2]), check_time(v[3])))

        ttk.Label(tab, text="Weekly hours = all the time you want to spend on it (class + outside class). "
                            "Example: Mathematics 10 h = 6 h of class + 4 h of homework.").pack(anchor="w")
        subjects = Section(
            tab, "Subjects", [("Subject", None), ("Weekly hours", None)],
            lambda: [(s.name, s.weekly_hours) for s in d.subjects],
            create_subject, lambda i: d.subjects.pop(i), self.changed)
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
            replace(d.rules, i, dm.Rule(v[0], text_to_days(v[1]), check_time(v[2]), check_time(v[3])))

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
            t = dm.Task(v[0], v[1], v[2], int(v[3]), float(v[4]), float(v[5] or 0.5))
            t.due_dt  # checks the date
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
        ttk.Label(bar, text="  Show:").pack(side="left")
        for text, value in (("A*", "astar"), ("Utility-based agent", "utility")):
            ttk.Radiobutton(bar, text=text, value=value, variable=self.mode, command=self.replan).pack(side="left")
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

    # ---------- summary ----------
    def _tab_summary(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="5. Summary and comparison")

        def table(title, cols, height):
            ttk.Label(tab, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(8, 0))
            t = ttk.Treeview(tab, columns=cols, show="headings", height=height)
            for col in cols:
                t.heading(col, text=col)
                t.column(col, width=150, anchor="w")
            t.pack(fill="x")
            return t

        self.t_priority = table("What should I do first? (utility-based agent, seen from now)",
                                ("Task", "Subject", "Due", "Hours", "U", "Urgency"), 7)
        self.t_priority.tag_configure("risk", foreground="red")
        self.t_compare = table("When each task finishes with each agent",
                               ("Task", "Due", "Finishes with A*", "Late hours A*",
                                "Finishes with utility", "Late hours utility"), 7)
        self.t_subjects = table("Hours per subject in the plan shown",
                                ("Subject", "Weekly goal", "Class", "Planned outside class", "Missing"), 7)

    def _fill_summary(self, plans, blocks):
        for t in (self.t_priority, self.t_compare, self.t_subjects):
            t.delete(*t.get_children())
        for t, u, urg in agent.prioritize(self.d.tasks, blocks):
            self.t_priority.insert("", "end", tags=("risk",) if urg > 1 else (), values=(
                t.name + ("  (not enough time)" if urg > 1 else ""), t.subject, t.due, t.hours,
                f"{u:.2f}", f"{urg:.2f}"))
        a, u = plans["astar"], plans["utility"]
        when = lambda x: f"{dm.DAYS[x.weekday()][:3]} {x:%d %H:%M}" if x else "does not fit this week"
        for t in sorted(self.d.tasks, key=lambda t: t.due):
            self.t_compare.insert("", "end", values=(
                t.name, t.due, when(a.finishes.get(t.name)), a.late_hours.get(t.name, 0),
                when(u.finishes.get(t.name)), u.late_hours.get(t.name, 0)))
        for s in self.d.subjects:
            in_class = dm.class_hours(self.d, s.name)
            outside = self.plan.study.get(s.name, 0)
            self.t_subjects.insert("", "end", values=(
                s.name, s.weekly_hours, in_class, outside, max(0, s.weekly_hours - in_class - outside)))

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
        plans = {m: agent.plan(self.d, blocks, m) for m in ("astar", "utility")}
        self.plan = plans[self.mode.get()]
        a, u = plans["astar"], plans["utility"]
        self.stats.config(text=(
            f"Cost  A*: {a.cost:.2f}  ({sum(a.late_hours.values())} h late, {a.nodes} nodes, {a.ms:.1f} ms)"
            f"     |     Utility-based agent: {u.cost:.2f}  ({sum(u.late_hours.values())} h late, "
            f"{u.nodes} decisions, {u.ms:.1f} ms)     |     {len(blocks)} free hours in 7 days"))
        needed = sum(t.hours for t in self.d.tasks) + sum(
            max(0, s.weekly_hours - dm.class_hours(self.d, s.name)) for s in self.d.subjects)
        self.warning.config(text="" if needed <= len(blocks) else
                            f"Warning: you need {needed:.0f} h outside class but only have {len(blocks)} free hours.")
        self._draw(since, dm.busy_blocks(self.d, since))
        self._fill_summary(plans, blocks)

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
