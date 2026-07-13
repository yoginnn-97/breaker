import asyncio
from datetime import date, datetime, timedelta

import flet as ft
import flet.canvas as cv

from backend import auth_logic as auth
from backend import config as cfg
from backend import journal, storage
from backend import charts

# ── palette ──────────────────────────────────────────────────────────────────
ACCENT = "#F2A65A"
BG_TOP = "#2e2a56"
BG_MID = "#7d6a9e"
BG_LOW = "#e8a9a0"
BG_BOT = "#f6e2c4"
PALETTE = ["#46C2A0","#5AA9E6","#E2735C","#9B8CFF","#E3B23C","#E667A0","#7C8AA3"]

# ── compat helpers ────────────────────────────────────────────────────────────
def border_all(w, c):
    s = ft.BorderSide(width=w, color=c)
    return ft.Border(top=s, right=s, bottom=s, left=s)

def align(x, y):                   return ft.alignment.Alignment(x, y)
def pad_sym(h=0, v=0):             return ft.padding.Padding(left=h, right=h, top=v, bottom=v)
def pad_only(l=0, t=0, r=0, b=0): return ft.padding.Padding(left=l, top=t, right=r, bottom=b)

A_CENTER = align(0, 0)
A_TOP    = align(0, -1)
A_BOT    = align(0,  1)

def greeting():
    h = datetime.now().hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")

# ── mountain background ───────────────────────────────────────────────────────
_FAR  = [(0,260),(0,150),(60,120),(120,175),(170,90),(220,150),(260,110),(300,150),(300,260)]
_NEAR = [(0,260),(0,190),(70,220),(140,140),(210,210),(260,160),(300,200),(300,260)]

def _mtn_path(pts, W, H, color, opacity):
    def s(p): return (p[0]/300*W, p[1]/260*H)
    sc  = [s(p) for p in pts]
    els = [cv.Path.MoveTo(*sc[0])] + [cv.Path.LineTo(*p) for p in sc[1:]] + [cv.Path.Close()]
    return cv.Path(els, paint=ft.Paint(
        color=ft.Colors.with_opacity(opacity, color),
        style=ft.PaintingStyle.FILL))

def mountain_canvas(W=1100, H=300):
    return cv.Canvas([
        _mtn_path(_FAR,  W, H, "#4a3f6b", 0.55),
        _mtn_path(_NEAR, W, H, "#332b52", 0.85),
    ], width=W, height=H)

# ── shared UI primitives ──────────────────────────────────────────────────────
def glass(content, padding=16, radius=18, expand=False):
    return ft.Container(
        content=content, padding=padding,
        border_radius=radius, expand=expand,
        bgcolor=ft.Colors.with_opacity(0.18, "#ffffff"),
        border=border_all(1, ft.Colors.with_opacity(0.28, "#ffffff")))

def stat_tile(label, txt: ft.Text):
    return glass(ft.Column([
        ft.Text(label.upper(), size=10, color=ft.Colors.with_opacity(0.65, "#fff")),
        txt], spacing=4), padding=14)

def section_title(text):
    return ft.Text(text, size=11, weight=ft.FontWeight.W_500,
                   color=ft.Colors.with_opacity(0.60, "#fff"))

def chip(label, selected=False, on_click=None, color=None):
    bg  = color or ("#ffffffee" if selected else ft.Colors.with_opacity(0.18, "#fff"))
    col = "#3a2e6e" if selected and not color else "#fff"
    return ft.Container(
        content=ft.Text(label, size=12, color=col,
                        weight=ft.FontWeight.W_500 if selected else ft.FontWeight.NORMAL),
        bgcolor=bg, padding=pad_sym(h=14, v=7),
        border_radius=999, on_click=on_click)


# ── main app ──────────────────────────────────────────────────────────────────
class BreakerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Breaker"
        self.page.padding = 0
        self.page.window.width  = 1100
        self.page.window.height = 720
        self.page.window.resizable = True

        self.user        = None
        self._c1_x       = 80.0
        self._c2_x       = 320.0
        self._cloud1     = ft.Container(top=55,  width=160, height=44, border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.30, "#fff"), blur=ft.Blur(8, 8))
        self._cloud2     = ft.Container(top=115, width=110, height=30, border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.20, "#fff"), blur=ft.Blur(6, 6))
        self._cloud_task = None
        self._timer_task = None
        self._current_tab = "dashboard"

        self.show_login()

    # ── background ───────────────────────────────────────────────────────────
    def _make_bg(self):
        self._cloud1.left = self._c1_x
        self._cloud2.left = self._c2_x
        return ft.Stack([
            ft.Container(expand=True, gradient=ft.LinearGradient(
                begin=A_TOP, end=A_BOT, colors=[BG_TOP, BG_MID, BG_LOW, BG_BOT])),
            ft.Container(top=-80, right=-60, width=260, height=260,
                shape=ft.BoxShape.CIRCLE,
                bgcolor=ft.Colors.with_opacity(0.45, "#f9dfa0"),
                blur=ft.Blur(40, 40)),
            self._cloud1,
            self._cloud2,
            ft.Container(content=mountain_canvas(), bottom=0, left=0, right=0),
        ], expand=True)

    async def _cloud_loop(self):
        while True:
            self._c1_x = (self._c1_x + 0.4) % 1500
            self._c2_x = (self._c2_x + 0.22) % 1500
            if self._c1_x > 1300: self._c1_x = -200
            if self._c2_x > 1300: self._c2_x = -160
            self._cloud1.left = self._c1_x
            self._cloud2.left = self._c2_x
            self.page.update()
            await asyncio.sleep(0.05)

    def _start_clouds(self):
        if self._cloud_task and not self._cloud_task.done():
            return
        self._cloud_task = self.page.run_task(self._cloud_loop)

    # ── timer ─────────────────────────────────────────────────────────────────
    async def _timer_loop(self, start_time):
        while True:
            diff = datetime.now() - start_time
            secs = max(0, int(diff.total_seconds()))
            h, r = divmod(secs, 3600)
            m, s = divmod(r, 60)
            self.timer_text.value = f"{h:02d}:{m:02d}:{s:02d}"
            self.page.update()
            await asyncio.sleep(1)

    def _start_timer(self, start_time):
        if self._timer_task and not self._timer_task.done():
            return
        self._timer_task = self.page.run_task(self._timer_loop, start_time)

    def _stop_timer(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None

    # ── shared nav bar ────────────────────────────────────────────────────────
    def _nav(self, active):
        def icon_color(tab):
            return "#fff" if active == tab else ft.Colors.with_opacity(0.45, "#fff")

        return glass(ft.Row([
            ft.IconButton(ft.Icons.HOME_ROUNDED,
                icon_color=icon_color("dashboard"),
                tooltip="Dashboard",
                on_click=lambda e: self.show_dashboard()),
            ft.IconButton(ft.Icons.BAR_CHART_ROUNDED,
                icon_color=icon_color("analytics"),
                tooltip="Analytics",
                on_click=lambda e: self.show_analytics()),
            ft.IconButton(ft.Icons.MENU_BOOK_ROUNDED,
                icon_color=icon_color("journal"),
                tooltip="Journal",
                on_click=lambda e: self.show_journal()),
            ft.IconButton(ft.Icons.SETTINGS_ROUNDED,
                icon_color=icon_color("settings"),
                tooltip="Settings",
                on_click=lambda e: self.show_settings()),
            ft.Container(expand=True),
            ft.Text(f"👤  {self.user}", size=12,
                    color=ft.Colors.with_opacity(0.55, "#fff")),
        ], alignment=ft.MainAxisAlignment.START),
        padding=pad_sym(h=12, v=6))

    def _scaffold(self, body_content, active_tab):
        """Wraps content with the shared background + nav bar."""
        body = ft.Container(
            content=ft.Column([
                ft.Container(content=body_content,
                             padding=pad_sym(h=24), expand=True),
                ft.Container(content=self._nav(active_tab),
                             padding=pad_only(l=16, r=16, b=14)),
            ], expand=True),
            expand=True)
        return ft.Stack([self._make_bg(), body], expand=True)

    # ── login ─────────────────────────────────────────────────────────────────
    def show_login(self):
        self.page.controls.clear()
        tf = dict(border_color=ft.Colors.with_opacity(0.4,"#fff"), color="#fff",
                  label_style=ft.TextStyle(color=ft.Colors.with_opacity(0.7,"#fff")))

        uname = ft.TextField(label="Username", width=300, **tf)
        passw = ft.TextField(label="Password", password=True,
                             can_reveal_password=True, width=300, **tf)
        err   = ft.Text("", color="#ffb4a8", size=12)
        su    = ft.TextField(label="Username", width=300, **tf)
        sp    = ft.TextField(label="Password", password=True,
                             can_reveal_password=True, width=300, **tf)
        sk    = ft.TextField(label="Access key", password=True,
                             can_reveal_password=True, width=300, **tf)
        smsg  = ft.Text("", size=12)

        def do_login(e):
            if auth.check_password(uname.value.strip(), passw.value):
                self.user = uname.value.strip()
                self.show_dashboard()
            else:
                err.value = "Wrong username or password."
                self.page.update()

        def do_signup(e):
            ok, msg = auth.create_account(su.value.strip(), sp.value, sk.value)
            smsg.value = msg
            smsg.color = "#b7f0c9" if ok else "#ffb4a8"
            if ok:
                self.user = su.value.strip()
                self.show_dashboard()
            else:
                self.page.update()

        lcol = ft.Column([uname, passw, err,
            ft.FilledButton("Sign in", on_click=do_login, width=300)], spacing=12)
        scol = ft.Column([
            ft.Text("Enter the access key to create an account.",
                    size=12, color=ft.Colors.with_opacity(0.65,"#fff")),
            su, sp, sk, smsg,
            ft.FilledButton("Create account", on_click=do_signup, width=300)],
            spacing=12, visible=False)

        toggle = ft.Row(spacing=4)
        def set_mode(signin):
            lcol.visible = signin; scol.visible = not signin
            toggle.controls = [
                ft.TextButton("Sign in",
                    style=ft.ButtonStyle(color="#fff" if signin else ft.Colors.with_opacity(0.45,"#fff")),
                    on_click=lambda e: set_mode(True)),
                ft.Text("·", color=ft.Colors.with_opacity(0.35,"#fff")),
                ft.TextButton("Create account",
                    style=ft.ButtonStyle(color="#fff" if not signin else ft.Colors.with_opacity(0.45,"#fff")),
                    on_click=lambda e: set_mode(False)),
            ]
            self.page.update()
        set_mode(True)

        card = glass(ft.Column([
            ft.Row([ft.Icon(ft.Icons.HOURGLASS_BOTTOM, color=ACCENT, size=28),
                    ft.Text("Breaker", size=26, weight=ft.FontWeight.W_500, color="#fff")]),
            ft.Text("Track. Reflect. Grow.", size=13,
                    color=ft.Colors.with_opacity(0.60,"#fff")),
            ft.Container(height=6), toggle, ft.Container(height=4),
            lcol, scol,
        ], spacing=8, tight=True, width=340), padding=30)

        self.page.add(ft.Stack([
            self._make_bg(),
            ft.Container(content=card, alignment=A_CENTER, expand=True),
        ], expand=True))
        self.page.update()
        self._start_clouds()

    # ── dashboard ─────────────────────────────────────────────────────────────
    def show_dashboard(self):
        self._stop_timer()
        self.page.controls.clear()

        self.categories = cfg.load_categories(self.user)
        self.settings   = cfg.load_settings(self.user)
        self.goal       = self.settings.get("daily_goal", 240)
        self.sel_cat    = self.categories[0] if self.categories else "Work"

        self.timer_text = ft.Text("00:00:00", size=32, weight=ft.FontWeight.W_500,
                                   color="#fff", font_family="monospace")
        self.timer_meta = ft.Text("", size=12, color=ft.Colors.with_opacity(0.7,"#fff"))
        self.today_stat = ft.Text("0m",  size=24, weight=ft.FontWeight.W_500, color="#fff")
        self.goal_stat  = ft.Text("0%",  size=24, weight=ft.FontWeight.W_500, color="#fff")
        self.sess_stat  = ft.Text("0",   size=24, weight=ft.FontWeight.W_500, color="#fff")
        self.task_field = ft.TextField(
            hint_text="What are you working on?", expand=True, height=46,
            border_radius=10,
            border_color=ft.Colors.with_opacity(0.35,"#fff"),
            hint_style=ft.TextStyle(color=ft.Colors.with_opacity(0.40,"#fff")),
            color="#fff")

        self.cat_row   = ft.Row(spacing=6, wrap=True)
        self._build_chips()
        self.ctrl_area = ft.Column(spacing=10)
        self._render_ctrl()

        all_df = storage.load_all(self.user)
        streak = journal.current_streak(all_df)
        streak_badge = ft.Row([
            ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED, color=ACCENT, size=16),
            ft.Text(f"{streak} day streak", size=13,
                    color=ft.Colors.with_opacity(0.85,"#fff"))
        ], spacing=4) if streak > 0 else ft.Container()

        body = ft.Column([
            ft.Container(height=20),
            ft.Row([
                ft.Column([
                    ft.Text(greeting(), size=26,
                            weight=ft.FontWeight.W_500, color="#fff"),
                    ft.Text(date.today().strftime("%A, %B %d"), size=13,
                            color=ft.Colors.with_opacity(0.60,"#fff")),
                ], spacing=2),
                streak_badge,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(height=16),
            glass(ft.Column([
                section_title("START A SESSION"),
                self.cat_row,
                self.ctrl_area,
            ], spacing=12)),
            ft.Container(height=14),
            ft.Row([
                stat_tile("Today",    self.today_stat),
                stat_tile("Goal",     self.goal_stat),
                stat_tile("Sessions", self.sess_stat),
            ], spacing=12),
        ], spacing=0, expand=True)

        self.page.add(self._scaffold(body, "dashboard"))
        self._refresh_stats()
        self.page.update()
        active = storage.get_active_session(self.user)
        if active:
            self._render_ctrl()
            self.page.update()
        self._start_clouds()

    def _build_chips(self):
        self.cat_row.controls.clear()
        for cat in self.categories:
            sel = cat == self.sel_cat
            self.cat_row.controls.append(chip(cat, selected=sel,
                on_click=lambda e, c=cat: self._pick_cat(c)))

    def _pick_cat(self, cat):
        self.sel_cat = cat; self._build_chips(); self.page.update()

    def _render_ctrl(self):
        self.ctrl_area.controls.clear()
        active = storage.get_active_session(self.user)
        if active:
            label = active["task"] or active["category"]
            self.timer_meta.value = f"Tracking  {label}"
            self.ctrl_area.controls += [
                ft.Row([
                    ft.Container(
                        content=ft.Icon(ft.Icons.HOURGLASS_BOTTOM, color=ACCENT, size=20),
                        width=46, height=46, border_radius=23,
                        bgcolor=ft.Colors.with_opacity(0.22, ACCENT), alignment=A_CENTER),
                    ft.Column([self.timer_meta, self.timer_text], spacing=0),
                ], spacing=12),
                ft.FilledButton("⏹  End & save session",
                    style=ft.ButtonStyle(bgcolor="#e2735c", color="#fff"),
                    on_click=self._end_session),
            ]
            self._start_timer(active["start_time"])
        else:
            self.ctrl_area.controls.append(
                ft.Row([self.task_field,
                        ft.FilledButton("▶  Start", on_click=self._start_session)], spacing=8))

    def _start_session(self, e):
        storage.start_active_session(self.sel_cat, self.task_field.value.strip(), self.user)
        self._render_ctrl(); self._refresh_stats(); self.page.update()

    def _end_session(self, e):
        self._stop_timer()
        active = storage.get_active_session(self.user)
        if active:
            storage.save_session(active["category"], active["task"],
                                 active["start_time"], datetime.now(), self.user)
            storage.clear_active_session(self.user)
        self._render_ctrl(); self._refresh_stats(); self.page.update()

    def _refresh_stats(self):
        df    = storage.load_for_date(date.today(), self.user)
        stats = journal.day_stats(df, self.goal)
        total = stats["total"]
        self.today_stat.value = f"{int(total)}m" if total >= 1 else f"{total}m"
        self.goal_stat.value  = f"{int(stats['progress']*100)}%"
        self.sess_stat.value  = str(stats["sessions"])

    # ── analytics ─────────────────────────────────────────────────────────────
    def show_analytics(self):
        self.page.controls.clear()
        all_rows = storage.load_all(self.user)

        streak   = journal.current_streak(all_rows)
        extremes = journal.session_extremes(all_rows)
        total_all = round(sum(r["duration_min"] for r in all_rows), 1) if all_rows else 0

        def big_stat(label, value, sub=""):
            return glass(ft.Column([
                ft.Text(label.upper(), size=10, color=ft.Colors.with_opacity(0.60,"#fff")),
                ft.Text(str(value), size=28, weight=ft.FontWeight.W_500, color="#fff"),
                ft.Text(sub, size=11, color=ft.Colors.with_opacity(0.55,"#fff")) if sub else ft.Container(),
            ], spacing=3), padding=16)

        h_all = int(total_all // 60)
        m_all = int(total_all % 60)
        top_row = ft.Row([
            big_stat("Streak",   f"{streak}d"),
            big_stat("Longest",  f"{extremes['longest']}m",  "session"),
            big_stat("Average",  f"{extremes['average']}m",  "session"),
            big_stat("All-time", f"{h_all}h {m_all}m"),
        ], spacing=12)

        # range toggle state
        self._analytics_range = getattr(self, "_analytics_range", "7d")

        range_row   = ft.Row(spacing=8)
        chart_area  = ft.Column(spacing=14)

        def build_charts(rng):
            self._analytics_range = rng
            days = 7 if rng == "7d" else 30
            trend_data = journal.weekly_trend(all_rows, days=days)
            cat_data   = journal.category_totals(all_rows, days=days)

            chart_fn   = charts.bar_trend if days == 7 else charts.line_trend
            trend_img  = chart_fn(trend_data)
            donut_img  = charts.donut_chart(cat_data)

            chart_area.controls = [
                glass(ft.Column([
                    section_title(f"{days}-DAY TREND"),
                    ft.Container(height=8),
                    trend_img,
                ], spacing=0)),
                glass(ft.Column([
                    section_title("BY CATEGORY"),
                    ft.Container(height=8),
                    donut_img if cat_data else
                        ft.Text("No data yet.", size=13,
                                color=ft.Colors.with_opacity(0.55,"#fff")),
                ], spacing=0)),
            ]
            # rebuild toggle chips
            range_row.controls = [
                chip("7 days",  selected=rng=="7d",
                     on_click=lambda e: (build_charts("7d"), self.page.update())),
                chip("30 days", selected=rng=="30d",
                     on_click=lambda e: (build_charts("30d"), self.page.update())),
            ]

        build_charts(self._analytics_range)

        body = ft.Column([
            ft.Container(height=20),
            ft.Text("Analytics", size=26, weight=ft.FontWeight.W_500, color="#fff"),
            ft.Text("Your patterns over time.", size=13,
                    color=ft.Colors.with_opacity(0.55,"#fff")),
            ft.Container(height=16),
            top_row,
            ft.Container(height=14),
            range_row,
            ft.Container(height=10),
            chart_area,
        ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

        self.page.add(self._scaffold(body, "analytics"))
        self.page.update()
        self._start_clouds()

    # ── journal ───────────────────────────────────────────────────────────────
    def show_journal(self):
        self.page.controls.clear()
        self.settings = cfg.load_settings(self.user)
        self.goal     = self.settings.get("daily_goal", 240)

        self._journal_date = date.today()
        self._journal_body = ft.Column(spacing=14, expand=True,
                                        scroll=ft.ScrollMode.AUTO)
        self._load_journal()

        def prev_day(e):
            self._journal_date -= timedelta(days=1)
            self._load_journal()
            self.page.update()

        def next_day(e):
            if self._journal_date < date.today():
                self._journal_date += timedelta(days=1)
                self._load_journal()
                self.page.update()

        self._date_label = ft.Text(
            self._journal_date.strftime("%A, %B %d"),
            size=16, weight=ft.FontWeight.W_500, color="#fff")

        date_nav = ft.Row([
            ft.IconButton(ft.Icons.CHEVRON_LEFT,  icon_color="#fff", on_click=prev_day),
            self._date_label,
            ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color="#fff", on_click=next_day),
        ], spacing=4)

        body = ft.Column([
            ft.Container(height=20),
            ft.Text("Journal", size=26, weight=ft.FontWeight.W_500, color="#fff"),
            ft.Container(height=6),
            date_nav,
            ft.Container(height=10),
            self._journal_body,
        ], spacing=0, expand=True)

        self.page.add(self._scaffold(body, "journal"))
        self.page.update()
        self._start_clouds()

    def _load_journal(self):
        self._journal_body.controls.clear()
        if hasattr(self, "_date_label"):
            self._date_label.value = self._journal_date.strftime("%A, %B %d")

        df = storage.load_for_date(self._journal_date, self.user)
        if df is None:
            self._journal_body.controls.append(
                glass(ft.Text("Nothing logged on this day.",
                              size=13, color=ft.Colors.with_opacity(0.60,"#fff"))))
            return

        stats = journal.day_stats(df, self.goal)
        total = stats["total"]

        summary = glass(ft.Column([
            ft.Text(f"{'%g' % total}m across {stats['sessions']} session(s)", size=16,
                    weight=ft.FontWeight.W_500, color="#fff"),
            ft.Text(f"{int(stats['progress']*100)}% of {self.goal}m daily goal", size=12,
                    color=ft.Colors.with_opacity(0.65,"#fff")),
        ], spacing=4))

        session_rows = []
        for row in df:
            cat  = str(row["category"])
            task = str(row["task"])
            dur  = row["duration_min"]
            display = task if task.lower() != cat.lower() else cat
            i    = list({r["category"] for r in df}).index(cat) % len(PALETTE) if cat in {r["category"] for r in df} else 0
            session_rows.append(ft.Row([
                ft.Container(width=10, height=10, border_radius=5,
                             bgcolor=PALETTE[i]),
                ft.Text(f"[{cat}] {display}", size=13, color="#fff", expand=True),
                ft.Text(f"{row['start_time']} → {row['end_time']}", size=11,
                        color=ft.Colors.with_opacity(0.55,"#fff")),
                ft.Text(f"{'%g' % dur}m", size=12, color=ACCENT),
            ], spacing=8))

        sessions_card = glass(ft.Column([
            section_title("SESSIONS"),
            ft.Container(height=8),
            ft.Column(session_rows, spacing=10),
        ], spacing=0))

        # download markdown
        md, _ = journal.build_journal(df, self._journal_date, self.goal)
        dl_btn = ft.OutlinedButton(
            f"⬇  Download {self._journal_date.isoformat()}.md",
            style=ft.ButtonStyle(color="#fff",
                                  side=ft.BorderSide(1, ft.Colors.with_opacity(0.35,"#fff"))),
            on_click=lambda e: self._download_journal(md))

        self._journal_body.controls += [summary, sessions_card, dl_btn]

    def _download_journal(self, md):
        fname = f"breaker-journal-{self._journal_date.isoformat()}.md"
        import os, tempfile
        path = os.path.join(tempfile.gettempdir(), fname)
        with open(path, "w") as f:
            f.write(md)
        self.page.launch_url(f"file://{path}")

    # ── settings ──────────────────────────────────────────────────────────────
    def show_settings(self):
        self.page.controls.clear()
        settings   = cfg.load_settings(self.user)
        categories = cfg.load_categories(self.user)
        self.goal  = settings.get("daily_goal", 240)

        # daily goal
        goal_field = ft.TextField(
            value=str(self.goal), width=120,
            border_color=ft.Colors.with_opacity(0.4,"#fff"),
            color="#fff",
            label_style=ft.TextStyle(color=ft.Colors.with_opacity(0.7,"#fff")),
            keyboard_type=ft.KeyboardType.NUMBER)
        goal_msg = ft.Text("", size=12, color="#b7f0c9")

        def save_goal(e):
            try:
                v = int(goal_field.value)
                settings["daily_goal"] = v
                cfg.save_settings(settings, self.user)
                self.goal = v
                goal_msg.value = "Saved ✓"
            except ValueError:
                goal_msg.value = "Enter a valid number."
                goal_msg.color = "#ffb4a8"
            self.page.update()

        goal_card = glass(ft.Column([
            section_title("DAILY GOAL (MINUTES)"),
            ft.Container(height=8),
            ft.Row([goal_field,
                    ft.FilledButton("Save", on_click=save_goal)], spacing=12),
            goal_msg,
        ], spacing=6))

        # categories
        cat_list_col = ft.Column(spacing=8)
        new_cat_field = ft.TextField(
            hint_text="e.g. Cooking", width=200,
            border_color=ft.Colors.with_opacity(0.4,"#fff"),
            hint_style=ft.TextStyle(color=ft.Colors.with_opacity(0.45,"#fff")),
            color="#fff")
        cat_msg = ft.Text("", size=12)

        def rebuild_cat_chips():
            cats = cfg.load_categories(self.user)
            cat_list_col.controls.clear()
            for cat in cats:
                def make_del(c):
                    def del_cat(e):
                        updated = [x for x in cfg.load_categories(self.user) if x != c]
                        if not updated: updated = ["Work"]
                        cfg.save_categories(updated, self.user)
                        rebuild_cat_chips()
                        self.page.update()
                    return del_cat
                cat_list_col.controls.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Text(cat, size=13, color="#fff", expand=True),
                                ft.IconButton(ft.Icons.CLOSE, icon_size=16,
                                              icon_color=ft.Colors.with_opacity(0.55,"#fff"),
                                              on_click=make_del(cat)),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=pad_sym(h=12, v=8),
                        border_radius=10,
                        bgcolor=ft.Colors.with_opacity(0.10, "#ffffff"),
                    )
                )

        rebuild_cat_chips()

        def add_cat(e):
            val = new_cat_field.value.strip()
            if not val:
                return
            cats = cfg.load_categories(self.user)
            if val not in cats:
                cats.append(val)
                cfg.save_categories(cats, self.user)
                new_cat_field.value = ""
                cat_msg.value = f"Added '{val}'"
                cat_msg.color = "#b7f0c9"
                rebuild_cat_chips()
                self.page.update()

        cat_card = glass(ft.Column([
            section_title("CATEGORIES"),
            ft.Container(height=8),
            cat_list_col,
            ft.Container(height=10),
            ft.Row([new_cat_field,
                    ft.FilledButton("Add", on_click=add_cat)], spacing=12),
            cat_msg,
        ], spacing=6))

        # danger zone
        confirm_check = ft.Checkbox(
            label="I understand this will delete all my data",
            label_style=ft.TextStyle(color=ft.Colors.with_opacity(0.75,"#fff")))
        danger_msg = ft.Text("", size=12)

        def clear_data(e):
            if not confirm_check.value:
                danger_msg.value = "Check the box first."
                danger_msg.color = "#ffb4a8"
                self.page.update()
                return
            storage.clear_all(self.user)
            danger_msg.value = "All data cleared."
            danger_msg.color = "#b7f0c9"
            confirm_check.value = False
            self.page.update()

        danger_card = ft.Container(
            content=ft.Column([
                section_title("DANGER ZONE"),
                ft.Container(height=8),
                ft.Text("Permanently deletes every logged session.",
                        size=12, color=ft.Colors.with_opacity(0.70,"#fff")),
                ft.Container(height=6),
                confirm_check,
                ft.FilledButton("Clear all data",
                    style=ft.ButtonStyle(bgcolor="#e2735c", color="#fff"),
                    on_click=clear_data),
                danger_msg,
            ], spacing=6),
            padding=16, border_radius=18,
            bgcolor=ft.Colors.with_opacity(0.18,"#E2735C"),
            border=border_all(1, ft.Colors.with_opacity(0.35,"#E2735C")))

        # account
        def logout(e):
            self._stop_timer()
            self.user = None
            self.show_login()

        account_card = glass(ft.Column([
            section_title("ACCOUNT"),
            ft.Container(height=8),
            ft.Text(f"Signed in as  {self.user}", size=13, color="#fff"),
            ft.Container(height=6),
            ft.OutlinedButton("Log out",
                style=ft.ButtonStyle(color="#fff",
                    side=ft.BorderSide(1, ft.Colors.with_opacity(0.35,"#fff"))),
                on_click=logout),
        ], spacing=6))

        body = ft.Column([
            ft.Container(height=20),
            ft.Text("Settings", size=26, weight=ft.FontWeight.W_500, color="#fff"),
            ft.Text("Preferences and data.", size=13,
                    color=ft.Colors.with_opacity(0.55,"#fff")),
            ft.Container(height=16),
            goal_card,
            ft.Container(height=12),
            cat_card,
            ft.Container(height=12),
            account_card,
            ft.Container(height=12),
            danger_card,
        ], spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

        self.page.add(self._scaffold(body, "settings"))
        self.page.update()
        self._start_clouds()


def main(page: ft.Page):
    BreakerApp(page)


if __name__ == "__main__":
    ft.app(target=main)