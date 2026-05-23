"""Plotting utilities — static convergence plots and live monitor."""

from __future__ import annotations

import statistics
import sys
from typing import Any


def _force_stats(values: list[float], window: int = 100) -> dict[str, float]:
    """Compute stats over the last `window` values."""
    if len(values) < 10:
        return {"avg": 0, "std": 0, "pct": 0, "min": 0, "max": 0, "last": 0}
    w = min(window, len(values))
    win = values[-w:]
    avg = statistics.mean(win)
    std = statistics.stdev(win) if w > 1 else 0
    pct = (std / abs(avg) * 100) if avg != 0 else 0
    return {
        "avg": avg,
        "std": std,
        "pct": pct,
        "min": min(win),
        "max": max(win),
        "last": values[-1],
    }


def plot_forces(
    times: list[float],
    drags: list[float],
    downforces: list[float],
    drag_axis: str,
    df_axis: str,
    save: bool = False,
) -> None:
    """Static convergence plot."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        sys.exit("ERROR: pip install matplotlib (or: pip install cfd-gen[plot])")

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    axes[0].plot(times, drags, "b-", linewidth=0.8)
    axes[0].set_ylabel(f"Drag [{drag_axis}] (N)")
    axes[0].grid(True, alpha=0.3)
    axes[0].set_title("Force Convergence")

    axes[1].plot(times, downforces, "r-", linewidth=0.8)
    axes[1].set_ylabel(f"Downforce [{df_axis}] (N)")
    axes[1].set_xlabel("Iteration")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    if save:
        plt.savefig("force_convergence.png", dpi=150, bbox_inches="tight")
        print("  Saved: force_convergence.png")
    else:
        plt.show()


def live_monitor(config_path: str | None, interval: float = 3) -> None:
    """Real-time animated force/residual monitor with stats overlay."""
    try:
        import matplotlib.animation as animation
        import matplotlib.pyplot as plt
        from matplotlib.widgets import Button
    except ImportError:
        sys.exit("ERROR: pip install matplotlib (or: pip install cfd-gen[plot])")

    from cfd_gen.postproc.forces import (
        axis_index_sign,
        check_convergence,
        find_force_files,
        load_axis_config,
        read_forces,
    )
    from cfd_gen.postproc.residuals import find_residual_files, read_residuals

    drag_idx, drag_sign, df_idx, df_sign, drag_axis, df_axis = load_axis_config(config_path)

    pages = ["Residuals", "Drag", "Downforce", "Summary"]
    state = {"page": 0}

    fig, ax = plt.subplots(figsize=(12, 7))
    plt.subplots_adjust(bottom=0.12, top=0.90, left=0.10, right=0.95)
    fig.canvas.manager.set_window_title("OpenFOAM Live Monitor")
    plt.rcParams.update({"font.size": 12})

    ax_prev = plt.axes([0.35, 0.02, 0.08, 0.04])
    ax_next = plt.axes([0.57, 0.02, 0.08, 0.04])
    btn_prev = Button(ax_prev, "< Prev")
    btn_next = Button(ax_next, "Next >")
    page_text = fig.text(0.5, 0.035, "", ha="center", fontsize=12, color="gray")

    def update_indicator():
        p = state["page"]
        dots = "  ".join("●" if i == p else "○" for i in range(len(pages)))
        page_text.set_text(f"{pages[p]}   {dots}")

    def go_prev(event=None):
        state["page"] = (state["page"] - 1) % len(pages)
        update_indicator()

    def go_next(event=None):
        state["page"] = (state["page"] + 1) % len(pages)
        update_indicator()

    def on_key(event):
        if event.key == "left":
            go_prev()
        elif event.key == "right":
            go_next()

    btn_prev.on_clicked(go_prev)
    btn_next.on_clicked(go_next)
    fig.canvas.mpl_connect("key_press_event", on_key)

    def _stats_text(label: str, stats: dict, unit: str = "N") -> str:
        """Format stats as multi-line text."""
        return (
            f"Avg (last 100): {stats['avg']:.2f} {unit}\n"
            f"Last:           {stats['last']:.2f} {unit}\n"
            f"Variation:      ±{stats['pct']:.2f}%\n"
            f"Range:          [{stats['min']:.2f}, {stats['max']:.2f}] {unit}"
        )

    def draw(frame):
        ax.clear()
        p = state["page"]

        if p == 0:  # Residuals
            res_files = find_residual_files()
            if not res_files:
                ax.text(0.5, 0.5, "Waiting for residual data...",
                        ha="center", va="center", transform=ax.transAxes)
                return []
            data, headers = read_residuals(res_files)
            t = data.get("Time", [])
            if not t:
                return []
            ax.set_yscale("log")
            ax.set_ylabel("Residual")
            ax.set_xlabel("Iteration")
            ax.grid(True, alpha=0.3)
            colors = plt.cm.tab10.colors
            ci = 0
            legend_labels = []
            for key in headers:
                if "initial" in key.lower() and key != "Time":
                    vals = data.get(key, [])
                    if vals and any(v and v > 0 for v in vals):
                        label = key.replace("_initial", "")
                        last_val = vals[-1] if vals[-1] and vals[-1] > 0 else 0
                        display = f"{label} ({last_val:.1e})"
                        ax.plot(t[:len(vals)], vals, linewidth=1.0,
                                label=display, color=colors[ci % len(colors)])
                        ci += 1
            ax.legend(loc="upper right", fontsize=11)
            ax.set_title(f"Residuals | {len(t)} iters", fontweight="bold", fontsize=14)

        elif p == 1:  # Drag
            files = find_force_files()
            if not files:
                ax.text(0.5, 0.5, "Waiting...", ha="center", va="center",
                        transform=ax.transAxes)
                return []
            times, drags, _ = read_forces(files, drag_idx, drag_sign, df_idx, df_sign)
            if not times:
                return []

            stats = _force_stats(drags)
            ax.plot(times, drags, "b-", linewidth=0.8, alpha=0.7)

            # Running average line
            if len(drags) > 50:
                window = 100
                avg_line = []
                for i in range(len(drags)):
                    start = max(0, i - window + 1)
                    avg_line.append(statistics.mean(drags[start:i+1]))
                ax.plot(times, avg_line, "b-", linewidth=2.0, label="Avg (100)")

            # Average band
            if stats["avg"] != 0:
                ax.axhline(stats["avg"], color="navy", linestyle="--", alpha=0.5)
                ax.axhspan(stats["min"], stats["max"], alpha=0.05, color="blue")

            ax.set_ylabel("Drag [N]")
            ax.set_xlabel("Iteration")
            ax.grid(True, alpha=0.3)

            conv_str = "✓ CONVERGED" if stats["pct"] < 0.5 else f"±{stats['pct']:.2f}%"
            ax.set_title(
                f"Drag ({drag_axis})  |  Avg: {stats['avg']:.2f} N  |  Var: {conv_str}  |  "
                f"Range: [{stats['min']:.2f}, {stats['max']:.2f}]  |  {len(times)} iters",
                fontweight="bold", fontsize=13,
            )

        elif p == 2:  # Downforce
            files = find_force_files()
            if not files:
                ax.text(0.5, 0.5, "Waiting...", ha="center", va="center",
                        transform=ax.transAxes)
                return []
            times, drags, dfs = read_forces(files, drag_idx, drag_sign, df_idx, df_sign)
            if not times:
                return []

            stats = _force_stats(dfs)
            d_stats = _force_stats(drags)
            ax.plot(times, dfs, "r-", linewidth=0.8, alpha=0.7)

            # Running average line
            if len(dfs) > 50:
                window = 100
                avg_line = []
                for i in range(len(dfs)):
                    start = max(0, i - window + 1)
                    avg_line.append(statistics.mean(dfs[start:i+1]))
                ax.plot(times, avg_line, "r-", linewidth=2.0, label="Avg (100)")

            # Average band
            if stats["avg"] != 0:
                ax.axhline(stats["avg"], color="darkred", linestyle="--", alpha=0.5)
                ax.axhspan(stats["min"], stats["max"], alpha=0.05, color="red")

            ax.set_ylabel("Downforce [N]")
            ax.set_xlabel("Iteration")
            ax.grid(True, alpha=0.3)

            # Stats in title
            ld = abs(stats["avg"] / d_stats["avg"]) if d_stats["avg"] != 0 else 0
            conv_str = "✓ CONVERGED" if stats["pct"] < 0.5 else f"±{stats['pct']:.2f}%"
            ax.set_title(
                f"Downforce ({df_axis})  |  Avg: {stats['avg']:.2f} N  |  Var: {conv_str}  |  "
                f"L/D: {ld:.2f}  |  {len(times)} iters",
                fontweight="bold", fontsize=13,
            )

        elif p == 3:  # Summary
            files = find_force_files()
            if not files:
                ax.text(0.5, 0.5, "Waiting...", ha="center", va="center",
                        transform=ax.transAxes)
                return []
            times, drags, dfs = read_forces(files, drag_idx, drag_sign, df_idx, df_sign)
            if not times:
                return []

            d_stats = _force_stats(drags)
            f_stats = _force_stats(dfs)
            ld = abs(f_stats["avg"] / d_stats["avg"]) if d_stats["avg"] != 0 else 0
            conv, dp, fp, da, fa = check_convergence(drags, dfs)

            ax.axis("off")
            summary = (
                f"{'═' * 50}\n"
                f"  FORCE SUMMARY  ({len(times)} iterations)\n"
                f"{'═' * 50}\n"
                f"\n"
                f"  Drag ({drag_axis}):\n"
                f"    Average:    {d_stats['avg']:>10.3f} N\n"
                f"    Last:       {d_stats['last']:>10.3f} N\n"
                f"    Variation:  {d_stats['pct']:>10.2f} %\n"
                f"    Range:      [{d_stats['min']:.2f}, {d_stats['max']:.2f}] N\n"
                f"\n"
                f"  Downforce ({df_axis}):\n"
                f"    Average:    {f_stats['avg']:>10.3f} N\n"
                f"    Last:       {f_stats['last']:>10.3f} N\n"
                f"    Variation:  {f_stats['pct']:>10.2f} %\n"
                f"    Range:      [{f_stats['min']:.2f}, {f_stats['max']:.2f}] N\n"
                f"\n"
                f"  L/D:          {ld:>10.3f}\n"
                f"\n"
                f"{'─' * 50}\n"
                f"  Status: {'✓ CONVERGED' if conv else '✗ NOT CONVERGED'}\n"
                f"  (threshold: ±0.5% over last 100 iters)\n"
                f"\n"
                f"  Note: If half-model (symmetry), multiply forces by 2.\n"
                f"{'═' * 50}"
            )
            ax.text(0.05, 0.95, summary, transform=ax.transAxes,
                    fontsize=13, verticalalignment="top", fontfamily="monospace",
                    bbox=dict(boxstyle="round", facecolor="white", alpha=0.9))
            ax.set_title("Summary", fontweight="bold", fontsize=14)

        update_indicator()
        return []

    update_indicator()
    _ = animation.FuncAnimation(fig, draw, interval=interval * 1000, cache_frame_data=False)
    print(f"  Live monitor (update every {interval}s) | ← → to switch pages")
    plt.show()
