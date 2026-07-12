import asyncio
from datetime import date, datetime, timedelta

import flet as ft
import flet.canvas as cv

from backend import auth_logic as auth
from backend import config as cfg
from backend import journal, storage
from backend.constants import PALETTE

# ── palette ──────────────────────────────────────────────────────────────────
ACCENT = "#F2A65A"
BG_TOP = "#2e2a56"
BG_MID = "#7d6a9e"
BG_LOW = "#e8a9a0"
BG_BOT = "#f6e2c4"

# ── compat helpers (Flet 0.85 dataclass API) ─────────────────────────────────
def border_all(w, c):
    s = ft.BorderSide(width=w, color=c)
    return ft.Border(top=s, right=s, bottom=s, left=s)

def align(x, y):           return ft.alignment.Alignment(x, y)
def pad_sym(h=0, v=0):     return ft.padding.Padding(left=h, right=h, top=v, bottom=v)
def pad_only(l=0,t=0,r=0,b=0): return ft.padding.Padding(left=l, top=t, right=r, bottom=b)

A_CENTER = align(0,  0)
A_TOP    = align(0, -1)
A_BOT    = align(0,  1)

def greeting():
    h = datetime.now().hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")

# ── mountain canvas ───────────────────────────────────────────────────────────
_FAR  = [(0,260),(0,150),(60,120),(120,175),(170,90),(220,150),(260,110),(300,150),(300,260)]
_NEAR = [(0,260),(0,190),(70,220),(140,140),(210,210),(260,160),(300,200),(300,260)]

def _mtn_path(pts, W, H, color, opacity):
    def s(p): return (p[0]/300*W, p[1]/260*H)
    sc = [s(p) for p in pts]
    els = [cv.Path.MoveTo(*sc[0])] + [cv.Path.LineTo(*p) for p in sc[1:]] + [cv.Path.Close()]
    return cv.Path(els, paint=ft.Paint(
        color=ft.Colors.with_opacity(opacity, color),
        style=ft.PaintingStyle.FILL))

def mountain_canvas(W=1100, H=300):
    return cv.Canvas([_mtn_path(_FAR,W,H,"#4a3f6b",0.55),
                      _mtn_path(_NEAR,W,H,"#332b52",0.85)], width=W, height=H)

# ── glass card ────────────────────────────────────────────────────────────────
def glass(content, padding=16, radius=18, expand=False):
    return ft.Container(content=content, padding=padding,
        border_radius=radius, expand=expand,
        bgcolor=ft.Colors.with_opacity(0.18, "#ffffff"),
        border=border_all(1, ft.Colors.with_opacity(0.28, "#ffffff")))

def stat_tile(label, txt: ft.Text):
    return glass(ft.Column([
        ft.Text(label.upper(), size=10, color=ft.Colors.with_opacity(0.65, "#fff")),
        txt], spacing=4), padding=14)


# ── app ───────────────────────────────────────────────────────────────────────
class BreakerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Breaker"
        self.page.padding = 0
        self.page.window.width  = 1100
        self.page.window.height = 720
        self.page.window.resizable = True

        self.user = None

        # cloud state — shared across login and dashboard
        self._c1_x = 80.0
        self._c2_x = 320.0
        self._cloud1 = ft.Container(top=55,  width=160, height=44, border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.30, "#ffffff"), blur=ft.Blur(8, 8))
        self._cloud2 = ft.Container(top=115, width=110, height=30, border_radius=999,
            bgcolor=ft.Colors.with_opacity(0.20, "#ffffff"), blur=ft.Blur(6, 6))

        # async task handles so we can cancel them
        self._cloud_task  = None
        self._timer_task  = None

        self.show_login()

    # ── background scene ──────────────────────────────────────────────────────
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

    # ── async cloud loop ──────────────────────────────────────────────────────
    async def _cloud_loop(self):
        """Runs on the page's own asyncio event loop — no threading needed."""
        while True:
            self._c1_x += 0.4
            self._c2_x += 0.22
            if self._c1_x > 1300: self._c1_x = -200
            if self._c2_x > 1300: self._c2_x = -160
            self._cloud1.left = self._c1_x
            self._cloud2.left = self._c2_x
            self.page.update()
            await asyncio.sleep(0.05)   # 20 fps — smooth, not heavy

    def _start_cloud_loop(self):
        if self._cloud_task and not self._cloud_task.done():
            return
        self._cloud_task = self.page.run_task(self._cloud_loop)

    # ── async timer loop ──────────────────────────────────────────────────────
    async def _timer_loop(self, start_time: datetime):
        """Ticks every second on the page's event loop."""
        while True:
            diff  = datetime.now() - start_time
            secs  = max(0, int(diff.total_seconds()))
            h, r  = divmod(secs, 3600)
            m, s  = divmod(r, 60)
            self.timer_text.value = f"{h:02d}:{m:02d}:{s:02d}"
            self.page.update()
            await asyncio.sleep(1)

    def _start_timer(self, start_time: datetime):
        if self._timer_task and not self._timer_task.done():
            return
        self._timer_task = self.page.run_task(self._timer_loop, start_time)

    def _stop_timer(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None

    # ── nav bar (shared across every screen) ─────────────────────────────────
    def _nav(self, active):
        def color(name):
            return "#fff" if name == active else ft.Colors.with_opacity(0.5, "#fff")

        return glass(ft.Row([
            ft.IconButton(ft.Icons.HOME_ROUNDED, icon_color=color("home"),
                tooltip="Dashboard", on_click=lambda e: self.show_dashboard()),
            ft.IconButton(ft.Icons.BAR_CHART_ROUNDED, icon_color=color("analytics"),
                tooltip="Analytics", on_click=lambda e: self.show_analytics()),
            ft.IconButton(ft.Icons.MENU_BOOK_ROUNDED, icon_color=color("journal"),
                tooltip="Journal", on_click=lambda e: self.show_journal()),
            ft.IconButton(ft.Icons.SETTINGS_ROUNDED, icon_color=color("settings"),
                tooltip="Settings", on_click=lambda e: self.show_settings()),
            ft.Container(expand=True),
            ft.Text(f"👤  {self.user}", size=12,
                    color=ft.Colors.with_opacity(0.60, "#fff")),
        ], alignment=ft.MainAxisAlignment.START),
        padding=pad_sym(h=12, v=6))

    def _shell(self, body, active):
        """Shared page frame for Analytics/Journal/Settings — the dashboard
        keeps its own richer flow (live timer resume etc) below."""
        self._stop_timer()
        self.page.controls.clear()
        content = ft.Container(
            content=ft.Column([
                ft.Container(content=body, padding=pad_sym(h=24), expand=True),
                ft.Container(content=self._nav(active), padding=pad_only(l=16, r=16, b=14)),
            ], expand=True),
            expand=True)
        self.page.add(ft.Stack([self._make_bg(), content], expand=True))
        self.page.update()
        self._start_cloud_loop()

    # ── login ─────────────────────────────────────────────────────────────────
    def show_login(self):
        self.page.controls.clear()

        tf_style = dict(
            border_color=ft.Colors.with_opacity(0.4, "#fff"),
            color="#fff",
            label_style=ft.TextStyle(color=ft.Colors.with_opacity(0.7, "#fff")))

        uname = ft.TextField(label="Username", width=300, **tf_style)
        passw = ft.TextField(label="Password", password=True,
                             can_reveal_password=True, width=300, **tf_style)
        err   = ft.Text("", color="#ffb4a8", size=12)

        s_user = ft.TextField(label="Username", width=300, **tf_style)
        s_pass = ft.TextField(label="Password", password=True,
                              can_reveal_password=True, width=300, **tf_style)
        s_key  = ft.TextField(label="Access key", password=True,
                              can_reveal_password=True, width=300, **tf_style)
        s_msg  = ft.Text("", size=12)

        def do_login(e):
            if auth.check_password(uname.value.strip(), passw.value):
                self.user = uname.value.strip()
                self.show_dashboard()
            else:
                err.value = "Wrong username or password."
                self.page.update()

        def do_signup(e):
            ok, msg = auth.create_account(s_user.value.strip(), s_pass.value, s_key.value)
            s_msg.value = msg
            s_msg.color = "#b7f0c9" if ok else "#ffb4a8"
            if ok:
                self.user = s_user.value.strip()
                self.show_dashboard()
            else:
                self.page.update()

        login_col  = ft.Column([uname, passw, err,
            ft.FilledButton("Sign in", on_click=do_login, width=300)],
            spacing=12)
        signup_col = ft.Column([
            ft.Text("Enter the access key to create an account.",
                    size=12, color=ft.Colors.with_opacity(0.65, "#fff")),
            s_user, s_pass, s_key, s_msg,
            ft.FilledButton("Create account", on_click=do_signup, width=300)],
            spacing=12, visible=False)

        toggle = ft.Row(spacing=4)
        def set_mode(signin):
            login_col.visible  = signin
            signup_col.visible = not signin
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
                    color=ft.Colors.with_opacity(0.60, "#fff")),
            ft.Container(height=6),
            toggle,
            ft.Container(height=4),
            login_col, signup_col,
        ], spacing=8, tight=True, width=340), padding=30)

        self.page.add(ft.Stack([
            self._make_bg(),
            ft.Container(content=card, alignment=A_CENTER, expand=True),
        ], expand=True))
        self.page.update()
        self._start_cloud_loop()

    # ── dashboard ─────────────────────────────────────────────────────────────
    def show_dashboard(self):
        self._stop_timer()
        self.page.controls.clear()

        self.categories = cfg.load_categories(self.user)
        self.settings   = cfg.load_settings(self.user)
        self.goal       = self.settings.get("daily_goal", 240)
        self.sel_cat    = self.categories[0] if self.categories else "Work"

        # live controls
        self.timer_text = ft.Text("00:00:00", size=32, weight=ft.FontWeight.W_500,
                                   color="#fff", font_family="monospace")
        self.timer_meta = ft.Text("", size=12,
                                   color=ft.Colors.with_opacity(0.7, "#fff"))
        self.today_stat = ft.Text("0m",  size=24, weight=ft.FontWeight.W_500, color="#fff")
        self.goal_stat  = ft.Text("0%",  size=24, weight=ft.FontWeight.W_500, color="#fff")
        self.sess_stat  = ft.Text("0",   size=24, weight=ft.FontWeight.W_500, color="#fff")

        self.task_field = ft.TextField(
            hint_text="What are you working on?", expand=True, height=46,
            border_radius=10,
            border_color=ft.Colors.with_opacity(0.35, "#fff"),
            hint_style=ft.TextStyle(color=ft.Colors.with_opacity(0.40, "#fff")),
            color="#fff")

        self.cat_row   = ft.Row(spacing=6, wrap=True)
        self._build_chips()

        self.ctrl_area = ft.Column(spacing=10)
        self._render_ctrl()

        stats_row = ft.Row([
            stat_tile("Today",    self.today_stat),
            stat_tile("Goal",     self.goal_stat),
            stat_tile("Sessions", self.sess_stat),
        ], spacing=12)

        all_df = storage.load_all(self.user)
        streak = journal.current_streak(all_df)
        streak_badge = ft.Row([
            ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT_ROUNDED, color=ACCENT, size=16),
            ft.Text(f"{streak} day streak", size=13,
                    color=ft.Colors.with_opacity(0.85, "#fff"))
        ], spacing=4) if streak > 0 else ft.Container()

        header = ft.Row([
            ft.Column([
                ft.Text(greeting(), size=26, weight=ft.FontWeight.W_500, color="#fff"),
                ft.Text(date.today().strftime("%A, %B %d"), size=13,
                        color=ft.Colors.with_opacity(0.60, "#fff")),
            ], spacing=2),
            streak_badge,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        ctrl_card = glass(ft.Column([
            ft.Text("START A SESSION", size=10,
                    color=ft.Colors.with_opacity(0.60, "#fff")),
            self.cat_row,
            self.ctrl_area,
        ], spacing=12))

        body = ft.Column([
            ft.Container(height=20),
            header,
            ft.Container(height=16),
            ctrl_card,
            ft.Container(height=14),
            stats_row,
        ], spacing=0, expand=True)

        nav = self._nav("home")

        content = ft.Container(
            content=ft.Column([
                ft.Container(content=body, padding=pad_sym(h=24), expand=True),
                ft.Container(content=nav,  padding=pad_only(l=16,r=16,b=14)),
            ], expand=True),
            expand=True)

        self.page.add(ft.Stack([self._make_bg(), content], expand=True))
        self._refresh_stats()
        self.page.update()

        # resume timer if a session was already running (cross-device sync)
        active = storage.get_active_session(self.user)
        if active:
            self._render_ctrl()
            self.page.update()

        self._start_cloud_loop()

    # ── category chips ────────────────────────────────────────────────────────
    def _build_chips(self):
        self.cat_row.controls.clear()
        for cat in self.categories:
            sel = cat == self.sel_cat
            self.cat_row.controls.append(ft.Container(
                content=ft.Text(cat, size=12,
                    color="#3a2e6e" if sel else "#fff",
                    weight=ft.FontWeight.W_500 if sel else ft.FontWeight.NORMAL),
                bgcolor="#ffffffee" if sel else ft.Colors.with_opacity(0.18,"#fff"),
                padding=pad_sym(h=14, v=7), border_radius=999,
                on_click=lambda e, c=cat: self._pick_cat(c)))

    def _pick_cat(self, cat):
        self.sel_cat = cat
        self._build_chips()
        self.page.update()

    # ── ctrl area ─────────────────────────────────────────────────────────────
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
                        bgcolor=ft.Colors.with_opacity(0.22, ACCENT),
                        alignment=A_CENTER),
                    ft.Column([self.timer_meta, self.timer_text], spacing=0),
                ], spacing=12),
                ft.FilledButton("⏹  End & save session",
                    style=ft.ButtonStyle(bgcolor="#e2735c", color="#fff"),
                    on_click=self._end_session),
            ]
            # start the real async timer
            self._start_timer(active["start_time"])
        else:
            self.ctrl_area.controls.append(
                ft.Row([self.task_field,
                        ft.FilledButton("▶  Start",
                            on_click=self._start_session)], spacing=8))

    def _start_session(self, e):
        storage.start_active_session(self.sel_cat, self.task_field.value.strip(), self.user)
        self._render_ctrl()
        self._refresh_stats()
        self.page.update()

    def _end_session(self, e):
        self._stop_timer()
        active = storage.get_active_session(self.user)
        if active:
            storage.save_session(active["category"], active["task"],
                                 active["start_time"], datetime.now(), self.user)
            storage.clear_active_session(self.user)
        self._render_ctrl()
        self._refresh_stats()
        self.page.update()

    def _refresh_stats(self):
        df    = storage.load_for_date(date.today(), self.user)
        stats = journal.day_stats(df, self.goal)
        total = stats["total"]
        # show as whole minutes if >= 1, else show decimal
        self.today_stat.value = f"{int(total)}m" if total >= 1 else f"{total}m"
        self.goal_stat.value  = f"{int(stats['progress'] * 100)}%"
        self.sess_stat.value  = str(stats["sessions"])

    # ── analytics ─────────────────────────────────────────────────────────────
    def show_analytics(self):
        all_df   = storage.load_all(self.user)
        streak   = journal.current_streak(all_df)
        extremes = journal.session_extremes(all_df)
        trend_df = journal.weekly_trend(all_df, days=7)
        cat_df   = journal.category_totals(all_df, days=None)

        stat_row = ft.Row([
            stat_tile("Streak",  ft.Text(f"{streak}d", size=22, weight=ft.FontWeight.W_500, color="#fff")),
            stat_tile("Longest", ft.Text(f"{extremes['longest']}m", size=22, weight=ft.FontWeight.W_500, color="#fff")),
            stat_tile("Average", ft.Text(f"{extremes['average']}m", size=22, weight=ft.FontWeight.W_500, color="#fff")),
        ], spacing=10)

        max_minutes = max(int(trend_df["Minutes"].max()), 1)
        trend_bars = ft.Row([
            ft.Column([
                ft.Text(str(int(row.Minutes)), size=10, color=ft.Colors.with_opacity(0.7, "#fff")),
                ft.Container(height=max(6, int(row.Minutes / max_minutes * 90)), width=26,
                             bgcolor=ACCENT, border_radius=6),
                ft.Text(row.Day, size=10, color=ft.Colors.with_opacity(0.7, "#fff")),
            ], alignment=ft.MainAxisAlignment.END, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4)
            for row in trend_df.itertuples()
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND, vertical_alignment=ft.CrossAxisAlignment.END)

        if cat_df.empty:
            cat_rows = [ft.Text("No sessions logged yet.", size=13, color=ft.Colors.with_opacity(0.7, "#fff"))]
        else:
            max_cat = max(int(cat_df["Minutes"].max()), 1)
            cat_rows = []
            for i, row in enumerate(cat_df.itertuples()):
                color = PALETTE[i % len(PALETTE)]
                bar_w = max(10, int(row.Minutes / max_cat * 220))
                cat_rows.append(ft.Row([
                    ft.Container(ft.Text(row.Category, size=12, color="#fff"), width=110),
                    ft.Container(width=bar_w, height=14, bgcolor=color, border_radius=6),
                    ft.Text(f"{int(row.Minutes)}m", size=12, color=ft.Colors.with_opacity(0.7, "#fff")),
                ], spacing=8))

        body = ft.Column([
            ft.Container(height=20),
            ft.Text("Analytics", size=22, weight=ft.FontWeight.W_500, color="#fff"),
            ft.Container(height=14),
            stat_row,
            ft.Container(height=14),
            glass(ft.Column([
                ft.Text("LAST 7 DAYS", size=10, color=ft.Colors.with_opacity(0.6, "#fff")),
                ft.Container(height=8),
                trend_bars,
            ])),
            ft.Container(height=12),
            glass(ft.Column([
                ft.Text("CATEGORY BREAKDOWN", size=10, color=ft.Colors.with_opacity(0.6, "#fff")),
                ft.Container(height=8),
                ft.Column(cat_rows, spacing=10),
            ])),
        ], spacing=0, scroll=ft.ScrollMode.AUTO)
        self._shell(body, active="analytics")

    # ── journal ───────────────────────────────────────────────────────────────
    def show_journal(self):
        if not hasattr(self, "_journal_date"):
            self._journal_date = date.today()

        holder = ft.Column(spacing=10)
        date_label = ft.Text("", size=14, weight=ft.FontWeight.W_500, color="#fff")

        def render():
            holder.controls.clear()
            df = storage.load_for_date(self._journal_date, self.user)
            md, _ = journal.build_journal(df, self._journal_date, self.goal)
            date_label.value = self._journal_date.strftime("%A, %B %d, %Y")
            if md is None:
                holder.controls.append(ft.Text("Nothing logged that day.", size=13,
                                                color=ft.Colors.with_opacity(0.7, "#fff")))
            else:
                holder.controls.append(ft.Column(
                    [ft.Text(md, size=13, color="#fff", selectable=True)],
                    scroll=ft.ScrollMode.AUTO, height=320))
                copy_feedback = ft.Text("", size=11, color="#b7f0c9")

                def copy_it(e):
                    self.page.set_clipboard(md)
                    copy_feedback.value = "Copied."
                    self.page.update()

                holder.controls.append(ft.Row(
                    [ft.TextButton("Copy to clipboard", icon=ft.Icons.COPY_ROUNDED, on_click=copy_it),
                     copy_feedback], spacing=8))
            self.page.update()

        def go_prev(e):
            self._journal_date -= timedelta(days=1)
            render()

        def go_next(e):
            if self._journal_date < date.today():
                self._journal_date += timedelta(days=1)
                render()

        date_nav = ft.Row([
            ft.IconButton(ft.Icons.CHEVRON_LEFT_ROUNDED, icon_color="#fff", on_click=go_prev),
            date_label,
            ft.IconButton(ft.Icons.CHEVRON_RIGHT_ROUNDED, icon_color="#fff", on_click=go_next),
        ], alignment=ft.MainAxisAlignment.CENTER)

        body = ft.Column([
            ft.Container(height=20),
            ft.Text("Journal", size=22, weight=ft.FontWeight.W_500, color="#fff"),
            ft.Container(height=14),
            glass(ft.Column([date_nav, ft.Container(height=8), holder])),
        ], spacing=0)
        self._shell(body, active="journal")
        render()

    # ── settings ──────────────────────────────────────────────────────────────
    def show_settings(self):
        goal_field = ft.TextField(label="Daily goal (minutes)", value=str(self.goal), width=200,
                                   border_color=ft.Colors.with_opacity(0.4, "#fff"), color="#fff",
                                   label_style=ft.TextStyle(color=ft.Colors.with_opacity(0.7, "#fff")))
        goal_msg = ft.Text("", size=12, color="#b7f0c9")

        def save_goal(e):
            try:
                new_goal = int(goal_field.value)
            except (TypeError, ValueError):
                goal_msg.value, goal_msg.color = "Enter a whole number.", "#ffb4a8"
                self.page.update()
                return
            self.settings["daily_goal"] = new_goal
            cfg.save_settings(self.settings, self.user)
            self.goal = new_goal
            goal_msg.value, goal_msg.color = "Saved.", "#b7f0c9"
            self.page.update()

        cats_col = ft.Column(spacing=8)
        new_cat_field = ft.TextField(hint_text="e.g., Cooking", expand=True, height=42,
                                      color="#fff", border_color=ft.Colors.with_opacity(0.4, "#fff"))
        cat_msg = ft.Text("", size=12)

        def render_categories():
            cats_col.controls.clear()
            cats = cfg.load_categories(self.user)
            for c in cats:
                def remove(e, cat=c):
                    remaining = [x for x in cfg.load_categories(self.user) if x != cat]
                    if not remaining:
                        cat_msg.value, cat_msg.color = "You need at least one category.", "#ffb4a8"
                        self.page.update()
                        return
                    cfg.save_categories(remaining, self.user)
                    render_categories()
                    self.page.update()

                cats_col.controls.append(ft.Row([
                    ft.Container(content=ft.Text(c, size=13, color="#fff"),
                                 bgcolor=ft.Colors.with_opacity(0.14, "#fff"),
                                 padding=pad_sym(h=12, v=6), border_radius=999, expand=True),
                    ft.IconButton(ft.Icons.CLOSE_ROUNDED, icon_color="#ffb4a8", icon_size=18, on_click=remove),
                ], spacing=8))

        render_categories()

        def add_category(e):
            name, current = new_cat_field.value.strip(), cfg.load_categories(self.user)
            if not name:
                cat_msg.value, cat_msg.color = "Enter a name first.", "#ffb4a8"
            elif name in current:
                cat_msg.value, cat_msg.color = "That category already exists.", "#ffb4a8"
            else:
                cfg.save_categories(current + [name], self.user)
                new_cat_field.value = ""
                cat_msg.value, cat_msg.color = "Added.", "#b7f0c9"
                render_categories()
            self.page.update()

        confirm_check = ft.Checkbox(label="I understand this will delete all my data",
                                     label_style=ft.TextStyle(color="#fff", size=12))
        danger_msg = ft.Text("", size=12, color="#b7f0c9")

        def clear_data(e):
            if not confirm_check.value:
                return
            storage.clear_all(self.user)
            danger_msg.value = "All data cleared."
            confirm_check.value = False
            self.page.update()

        body = ft.Column([
            ft.Container(height=20),
            ft.Text("Settings", size=22, weight=ft.FontWeight.W_500, color="#fff"),
            ft.Container(height=14),
            glass(ft.Column([
                ft.Text("DAILY GOAL", size=10, color=ft.Colors.with_opacity(0.6, "#fff")),
                ft.Container(height=8),
                ft.Row([goal_field, ft.FilledButton("Save", on_click=save_goal)], spacing=10),
                goal_msg,
            ])),
            ft.Container(height=12),
            glass(ft.Column([
                ft.Text("CATEGORIES", size=10, color=ft.Colors.with_opacity(0.6, "#fff")),
                ft.Container(height=8),
                cats_col,
                ft.Container(height=8),
                ft.Row([new_cat_field, ft.FilledButton("Add", on_click=add_category)], spacing=8),
                cat_msg,
            ])),
            ft.Container(height=12),
            glass(ft.Column([
                ft.Text("DANGER ZONE", size=10, color="#ffb4a8"),
                ft.Container(height=8),
                ft.Text("This permanently deletes every logged session.", size=12,
                        color=ft.Colors.with_opacity(0.7, "#fff")),
                confirm_check,
                ft.FilledButton("Clear all data", icon=ft.Icons.DELETE_ROUNDED,
                                 style=ft.ButtonStyle(bgcolor="#e2735c", color="#fff"),
                                 on_click=clear_data),
                danger_msg,
            ])),
        ], spacing=0, scroll=ft.ScrollMode.AUTO)
        self._shell(body, active="settings")


def main(page: ft.Page):
    BreakerApp(page)


if __name__ == "__main__":
    ft.app(target=main)
