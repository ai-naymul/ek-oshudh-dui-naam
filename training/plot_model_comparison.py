"""Chart for 'why LightGBM': docs/model_comparison.png, drawn only from the saved reports.

Reads eval/reports/model_comparison.json (same features, rows and 2% rule for four model families) and, for the two
baselines, eval/reports/e1_policy_gemini-3.8-flash.json (R1 spelling match, R3 the AI picks). Run from backend/:
    uv run --with matplotlib python ../training/plot_model_comparison.py
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INK, INK2, MUTED, BAR, SURFACE = "#0b0b0b", "#52514e", "#898781", "#2a78d6", "#fcfcfb"


def main():
    cmp_ = json.load(open(os.path.join(ROOT, "eval", "reports", "model_comparison.json"), encoding="utf-8"))
    e1 = json.load(open(os.path.join(ROOT, "eval", "reports", "e1_policy_gemini-3.8-flash.json"), encoding="utf-8"))
    m = cmp_["models"]
    rows = [("LightGBM (ours, shipped)", m["LightGBM (shipped model file)"]),
            ("Random forest", m["Random forest"]),
            ("Logistic regression", m["Logistic regression"]),
            ("Neural network (MLP)", m["Neural network (MLP 32-16)"])]
    data = [(name, r["top1_test"], r["auto_accept"]) for name, r in rows]
    data += [("Gemini picks (R3)", e1["top1_test"]["R3"], e1["policies"]["R3"]["test"]["auto_accept_coverage"]),
             ("Spelling match only (R1)", e1["top1_test"]["R1"], e1["policies"]["R1"]["test"]["auto_accept_coverage"])]
    names = [d[0] for d in data][::-1]
    panels = [("Right medicine ranked first", [d[1] for d in data][::-1]),
              ("Accepted without asking (wrong ≤ 2%)", [d[2] for d in data][::-1])]

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4), sharey=True, facecolor=SURFACE)
    for ax, (title, vals) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        ax.barh(range(len(vals)), [v * 100 for v in vals], height=0.62, color=BAR, edgecolor=SURFACE, linewidth=2)
        for i, v in enumerate(vals):
            ax.text(v * 100 + 1.2, i, f"{v * 100:.1f}%", va="center", ha="left", color=INK, fontsize=11,
                    fontweight="bold" if names[i].startswith("LightGBM") else "normal")
        ax.set_xlim(0, 100)
        ax.set_title(title, color=INK, fontsize=12.5, pad=10)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], color=INK2)
        ax.grid(axis="x", color=MUTED, alpha=0.25, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", colors=MUTED)
    axes[0].set_yticks(range(len(names)))
    axes[0].set_yticklabels(names, color=INK)
    for lab in axes[0].get_yticklabels():
        if lab.get_text().startswith("LightGBM"):
            lab.set_fontweight("bold")
    fig.text(0.5, -0.04, "780 test words of Bangladeshi doctors' handwriting, read by Gemini 3.8 Flash. The four models "
             "share the same 14 features,\ntraining rows and accept rule (95% upper bound of wrong automatic accepts ≤ 2%, "
             "set on validation). Measured 23 Nov 2026.", ha="center", va="top", color=INK2, fontsize=10)
    out = os.path.join(ROOT, "docs", "model_comparison.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", pad_inches=0.3, facecolor=SURFACE)
    print("wrote", out)


if __name__ == "__main__":
    main()
