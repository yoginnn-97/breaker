"""
Renders charts as PNG bytes using matplotlib, returned as ft.Image.
All charts use the Breaker dusk palette and transparent backgrounds
so they look native inside the glass cards.
"""
import io
import base64

import matplotlib
matplotlib.use("Agg")   # no GUI needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import MaxNLocator
import flet as ft

# ── palette ───────────────────────────────────────────────────────────────────
ACCENT    = "#F2A65A"
FG        = "#E7ECF5"          # text / axis
FG_MUT    = "#7C8AA3"          # muted text
GRID      = "#1D2B45"
SERIES    = ["#46C2A0","#5AA9E6","#E2735C","#9B8CFF","#E3B23C","#E667A0"]


def _base_fig(w=7, h=2.6):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_alpha(0)
    ax.set_facecolor((0, 0, 0, 0))
    ax.tick_params(colors=FG_MUT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)
    return fig, ax


def _to_image(fig, width=None):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                transparent=True, dpi=110)
    plt.close(fig)
    buf.seek(0)
    return ft.Image(src=buf.read(), fit=ft.BoxFit.CONTAIN,
                    width=width, border_radius=10)


def bar_trend(trend_data, width=None):
    """Vertical bar chart from weekly_trend() output."""
    days    = [r["day"] for r in trend_data]
    minutes = [r["minutes"] for r in trend_data]
    max_v   = max(minutes) if minutes else 1

    fig, ax = _base_fig(w=7, h=2.4)
    colors  = [ACCENT if m == max_v and m > 0 else "#46C2A060" for m in minutes]
    bars    = ax.bar(days, minutes, color=colors, width=0.55,
                     linewidth=0, zorder=3)

    # value labels on top of bars
    for bar, val in zip(bars, minutes):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f"{int(val)}m", ha="center", va="bottom",
                    color=FG_MUT, fontsize=7)

    ax.set_ylim(0, max(max_v * 1.25, 5))
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    ax.yaxis.set_tick_params(labelcolor=FG_MUT)
    ax.set_xticks(range(len(days)))
    ax.set_xticklabels(days, color=FG_MUT, fontsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    fig.tight_layout(pad=0.4)
    return _to_image(fig, width=width)


def donut_chart(cat_data, width=None):
    """Donut chart from category_totals() output."""
    if not cat_data or sum(r["minutes"] for r in cat_data) <= 0:
        return ft.Text("No data yet.", size=12, color=FG_MUT)

    labels  = [r["category"] for r in cat_data]
    values  = [r["minutes"]  for r in cat_data]
    colors  = [SERIES[i % len(SERIES)] for i in range(len(labels))]
    total   = sum(values)

    fig, ax = _base_fig(w=4, h=3.2)
    wedges, _ = ax.pie(
        values, colors=colors,
        startangle=90,
        wedgeprops=dict(width=0.52, edgecolor="none"),
    )

    # centre label
    ax.text(0, 0, f"{int(total)}m", ha="center", va="center",
            fontsize=14, fontweight="bold", color=FG)
    ax.text(0, -0.22, "total", ha="center", va="center",
            fontsize=8, color=FG_MUT)

    # legend below
    patches = [mpatches.Patch(color=colors[i], label=f"{labels[i]}  {int(values[i])}m")
               for i in range(len(labels))]
    ax.legend(handles=patches, loc="lower center",
              bbox_to_anchor=(0.5, -0.22), ncol=2,
              fontsize=7.5, frameon=False,
              labelcolor=FG_MUT)

    fig.tight_layout(pad=0.3)
    return _to_image(fig, width=width)


def line_trend(trend_data, width=None):
    """Line chart for a 30-day trend."""
    days    = [r["day"] for r in trend_data]
    minutes = [r["minutes"] for r in trend_data]

    fig, ax = _base_fig(w=7, h=2.4)
    xs = range(len(days))
    ax.fill_between(xs, minutes, alpha=0.18, color=ACCENT)
    ax.plot(xs, minutes, color=ACCENT, linewidth=2, solid_capstyle="round")

    # only show a few x labels to avoid crowding
    step = max(1, len(days) // 7)
    ax.set_xticks(list(xs)[::step])
    ax.set_xticklabels(days[::step], color=FG_MUT, fontsize=7)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4))
    fig.tight_layout(pad=0.4)
    return _to_image(fig, width=width)