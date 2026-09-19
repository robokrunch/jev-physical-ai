#!/usr/bin/env python3
"""Charts for the Jev demos. All numbers from demo-a-results.json (measured)
plus labeled assumptions for the GPT-4o-mini baseline."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.size": 13, "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 100, "savefig.dpi": 100,
})
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data")
ASSETS = os.path.join(REPO_ROOT, "assets")

with open(os.path.join(DATA, "demo-a-results.json")) as f:
    A = json.load(f)["aggregate"]

JEV_PER_M = A["cost_usd"]["per_million_decisions"]          # 24.57 measured
GPT_IN, GPT_OUT = 0.15, 0.60                                 # $/Mtok, OpenRouter page
GPT_TOK = (600, 60)                                          # assumed triage size
GPT_PER_M = (GPT_TOK[0] * GPT_IN + GPT_TOK[1] * GPT_OUT)     # 126.0
DEC_PER_ROBOT_DAY = 48

def monthly_cost(robots, per_m):
    return robots * DEC_PER_ROBOT_DAY * 30 / 1e6 * per_m

# ---------------- chart 1: fleet cost ----------------
robots = [1_000, 10_000]
jev = [monthly_cost(r, JEV_PER_M) for r in robots]
gpt = [monthly_cost(r, GPT_PER_M) for r in robots]
x = np.arange(len(robots)); w = 0.36
fig, ax = plt.subplots(figsize=(12, 6.75))
b1 = ax.bar(x - w/2, jev, w, label=f"Jev decisions API (measured ${JEV_PER_M:.2f}/M)", color="#1f6feb")
b2 = ax.bar(x + w/2, gpt, w, label=f"GPT-4o-mini triage (assumed ${GPT_PER_M:.0f}/M)", color="#9e9e9e")
for b in list(b1) + list(b2):
    ax.text(b.get_x() + b.get_width()/2, b.get_height()*1.02,
            f"${b.get_height():,.0f}", ha="center", va="bottom", fontsize=12)
ax.set_xticks(x); ax.set_xticklabels(["1,000 robots", "10,000 robots"])
ax.set_ylabel("USD / month")
ax.set_title("Fleet triage cost: 48 decisions/robot/day, 30 days")
ax.legend(frameon=False, loc="upper left")
ax.text(0.0, -0.16, "Jev: 300 measured calls, mean 585 in-tokens @ $0.042/M.  GPT-4o-mini: $0.15/$0.60 per MTok (OpenRouter),\n"
        "assumed 600 in + 60 out tokens per triage incl. prompt + JSON parse. Ratio ≈ 5.1x.",
        transform=ax.transAxes, fontsize=10.5, color="#555", va="top", ha="left")
fig.tight_layout(); fig.savefig(os.path.join(ASSETS, "chart-fleet-cost.png"), bbox_inches="tight")
print("fleet chart:", [round(v,2) for v in jev], [round(v,2) for v in gpt])

# ---------------- chart 2: latency distribution ----------------
with open(os.path.join(DATA, "demo-a-results.json")) as f:
    recs = json.load(f)["records"]
lat = sorted(r["latency_s"] for r in recs if r["error"] is None)
fig, ax = plt.subplots(figsize=(12, 6.75))
ax.hist(lat, bins=30, color="#1f6feb", alpha=0.85, edgecolor="white")
for p, lab, c in [(0.50, "p50", "#d62728"), (0.95, "p95", "#ff7f0e")]:
    v = lat[min(len(lat)-1, int(p*len(lat)))]
    ax.axvline(v, color=c, ls="--", lw=2)
    ax.text(v, ax.get_ylim()[1]*0.92, f" {lab} {v:.2f}s", color=c, fontsize=12, va="top")
ax.set_xlabel("seconds per decision (3 questions, one API call)")
ax.set_ylabel("calls")
ax.set_title("Jev decisions API latency — 300 fleet-triage calls (this VM → OpenRouter → TypeSafe)")
ax.text(0.0, -0.16, "Measured 2026-09-19, n=300, 6-way concurrent. Includes network RTT from this VM; model P50 on OpenRouter page: 0.23s.",
        transform=ax.transAxes, fontsize=10.5, color="#555", va="top", ha="left")
fig.tight_layout(); fig.savefig(os.path.join(ASSETS, "chart-latency.png"), bbox_inches="tight")
print("latency chart done, n =", len(lat))
