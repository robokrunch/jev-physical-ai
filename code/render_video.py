#!/usr/bin/env python3
"""Render the Jev fleet-triage demo video frames (1280x720 PNGs) from real demo data."""
import json, math, os, random, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle

# ---------- constants (headlines verified from data/demo-a-results.json aggregate) ----------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data", "demo-a-results.json")
FRAMES_DIR = os.environ.get("JEV_FRAMES_DIR", os.path.join(REPO_ROOT, "frames"))  # temp render dir
ASSETS = os.path.join(REPO_ROOT, "assets")
FPS = 24
STREAM_FRAMES = 1200          # 300 events over 50 s
BG = "#0a0e14"
PANEL = "#11161f"
TXT = "#e6edf3"
DIM = "#8b949e"
GREEN = "#4ade80"
AMBER = "#fbbf24"
RED = "#f87171"

F_SANS = FontProperties(family="DejaVu Sans")
F_SANS_B = FontProperties(family="DejaVu Sans", weight="bold")
F_CJK = FontProperties(family="Noto Sans SC")          # feed (EN+ZH, no tofu)

d = json.load(open(DATA))
recs = d["records"]
agg = d["aggregate"]
assert len(recs) == 300, len(recs)
TOTAL_COST = sum(r["cost_usd"] for r in recs)
MEAN_LAT = sum(r["latency_s"] for r in recs) / len(recs)
print(f"total_cost={TOTAL_COST:.8f} (agg says {agg['cost_usd']['total']})  mean_lat={MEAN_LAT:.3f}")

random.seed(7)
use_zh = []
for r in recs:
    use_zh.append(bool(r.get("event_zh")) and random.random() < 0.35)

def trunc(s, n):
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n - 1] + "…"

def tstr(i):
    t = i * (50.0 / 300.0)
    return f"T+{int(t // 60):02d}:{t % 60:04.1f}"

def intervene_of(r):
    return r["answers"]["needs_intervention"]["noul"] >= 0.5

print("intervene YES count:", sum(1 for r in recs if intervene_of(r)))

# precompute per-event display rows
rows = []
for i, r in enumerate(recs):
    txt = r["event_zh"] if use_zh[i] else r["event_en"]
    a = r["answers"]
    team = a["team"]["choice"]
    urg = a["urgency"]["score"] if (a["urgency"]["type"] == "score") else 0.0
    iv = intervene_of(r)
    rows.append({
        "t": tstr(i),
        "feed": trunc(f"{r['robot_id']}  {txt}", 56),
        "dec": f"→ {'INTERVENE' if iv else 'OK'} · team:{team} · urg {urg:.1f}/2 · "
               f"{r['latency_s']:.2f}s · ${r['cost_usd']:.7f}",
        "iv": iv,
        "team": team.upper(),
        "urg": urg,
        "lat": r["latency_s"],
        "cost": r["cost_usd"],
        "in_tok": r["input_tokens"],
        "out_tok": r["output_tokens"],
        "robot": r["robot_id"],
        "short": trunc(txt, 46),
        "spot": (i % 10 == 0),
    })

os.makedirs(FRAMES_DIR, exist_ok=True)

# ---------------- figure & static chrome ----------------
fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
fig.patch.set_facecolor(BG)

def txt(x, y, s, fp=F_SANS, size=12, color=TXT, ha="left", va="center", alpha=1.0):
    return fig.text(x, y, s, fontproperties=fp, fontsize=size, color=color,
                    ha=ha, va=va, alpha=alpha)

# header
txt(0.03, 0.955, "JEV × ROBOT FLEET — LIVE TRIAGE", F_SANS_B, 16, TXT)
txt(0.03, 0.928, "300 real decisions-API calls · typesafe/jev-1.13 via OpenRouter", F_SANS, 10.5, DIM)
rec_dot = txt(0.965, 0.955, "● LIVE", F_SANS_B, 13, RED, ha="right")
fig.patches.extend([Rectangle((0.02, 0.908), 0.96, 0.002, transform=fig.transFigure,
                              facecolor="#1c2530", edgecolor="none")])
# feed title + right titles
txt(0.03, 0.882, "EVENT FEED — warehouse AMR fleet", F_SANS, 11, DIM)
fig.patches.extend([Rectangle((0.625, 0.12), 0.002, 0.78, transform=fig.transFigure,
                              facecolor="#1c2530", edgecolor="none")])
txt(0.65, 0.882, "LATEST DECISION", F_SANS, 11, DIM)
txt(0.65, 0.47, "RUNNING TOTALS", F_SANS, 11, DIM)
# ticker ($ escaped: matplotlib would treat $...$ as mathtext)
txt(0.03, 0.05, "p50 0.53s · p95 0.81s · \\$24.57 per 1M decisions · output tokens \\$0 · 300/300 calls OK",
    F_SANS, 11, DIM)
fig.patches.extend([Rectangle((0.02, 0.088), 0.96, 0.002, transform=fig.transFigure,
                              facecolor="#1c2530", edgecolor="none")])

# ---------------- dynamic artists ----------------
N_VIS = 9
LINE_H = 0.0375
FEED_TOP = 0.845
feed_evt, feed_dec = [], []
for _ in range(N_VIS):
    feed_evt.append(txt(0.035, 0, "", F_CJK, 13, TXT))
    feed_dec.append(txt(0.055, 0, "", F_CJK, 12, GREEN))
hl = Rectangle((0.025, 0), 0.585, 2 * LINE_H, transform=fig.transFigure,
               facecolor=AMBER, alpha=0.07, edgecolor=AMBER, linewidth=0.8)
hl.set_visible(False)
fig.patches.append(hl)

c_robot = txt(0.65, 0.83, "", F_SANS, 13, DIM)
c_evshort = txt(0.65, 0.795, "", F_CJK, 11, TXT)
c_verdict = txt(0.65, 0.70, "", F_SANS_B, 34, GREEN)
c_team = txt(0.65, 0.625, "", F_SANS, 14, TXT)
c_urg = txt(0.65, 0.582, "", F_SANS, 12.5, TXT)
c_call = txt(0.65, 0.54, "", F_SANS, 11, DIM)

t_n_lab = txt(0.65, 0.415, "DECISIONS", F_SANS, 11, DIM)
t_n = txt(0.65, 0.372, "", F_SANS_B, 26, TXT)
t_c_lab = txt(0.65, 0.305, "SPENT", F_SANS, 11, DIM)
t_c = txt(0.65, 0.262, "", F_SANS_B, 26, GREEN)
t_l_lab = txt(0.65, 0.195, "MEAN LATENCY", F_SANS, 11, DIM)
t_l = txt(0.65, 0.152, "", F_SANS_B, 26, TXT)

def urg_bar(score):
    n = 12
    f = int(round(score / 2 * n))
    return "[" + "#" * f + "-" * (n - f) + "]"

cum_cost = [0.0]
cum_lat = [0.0]

def draw_stream_frame(f):
    idx = min(299, f // 4)
    # feed window: last N_VIS events
    lo = max(0, idx - N_VIS + 1)
    hl.set_visible(False)
    for j in range(N_VIS):
        k = lo + j
        y = FEED_TOP - j * 2 * LINE_H
        if k <= idx:
            r = rows[k]
            feed_evt[j].set_position((0.035, y))
            feed_evt[j].set_text(f"{r['t']}  {r['feed']}")
            feed_dec[j].set_position((0.055, y - LINE_H))
            feed_dec[j].set_text(r["dec"])
            feed_dec[j].set_color(AMBER if r["iv"] else GREEN)
            if r["spot"]:
                hl.set_y(y - LINE_H - 0.004)
                hl.set_visible(True)
        else:
            feed_evt[j].set_text("")
            feed_dec[j].set_text("")
    # latest decision card
    r = rows[idx]
    c_robot.set_text(r["robot"])
    c_evshort.set_text(r["short"])
    c_verdict.set_text("INTERVENE" if r["iv"] else "OK — NO ACTION")
    c_verdict.set_fontsize(34 if r["iv"] else 25)
    c_verdict.set_color(AMBER if r["iv"] else GREEN)
    c_team.set_text(f"TEAM   {r['team']}")
    c_urg.set_text(f"URGENCY  {urg_bar(r['urg'])}  {r['urg']:.1f}/2")
    c_call.set_text(f"{r['lat']:.2f}s · ${r['cost']:.7f} · {r['in_tok']} in / {r['out_tok']} out tok")
    # counters
    n = idx + 1
    cc = sum(x["cost"] for x in rows[:n])
    ml = sum(x["lat"] for x in rows[:n]) / n
    t_n.set_text(f"{n} / 300")
    t_c.set_text(f"${cc:.5f}")
    t_l.set_text(f"{ml:.2f}s")
    # blinking REC
    rec_dot.set_alpha(1.0 if (f // 12) % 2 == 0 else 0.25)

def render_stream(frames):
    for f in frames:
        draw_stream_frame(f)
        fig.savefig(f"{FRAMES_DIR}/stream_{f:04d}.png", dpi=100, facecolor=BG)
        if f % 200 == 0:
            print(f"  frame {f}", flush=True)

def render_freeze():
    draw_stream_frame(STREAM_FRAMES - 1)
    # overlay sits over the feed area only; right card stays fully visible
    fig.text(0.31, 0.60, "STREAM COMPLETE", fontproperties=F_SANS_B, fontsize=30,
             color=TXT, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.6", facecolor="#000000", alpha=0.78, edgecolor="#1c2530"))
    fig.text(0.31, 0.53, f"300/300 decisions · ${TOTAL_COST:.5f} total · mean {MEAN_LAT:.2f}s",
             fontproperties=F_SANS, fontsize=15, color=DIM, ha="center", va="center",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#000000", alpha=0.78, edgecolor="#1c2530"))
    fig.savefig(f"{FRAMES_DIR}/freeze.png", dpi=100, facecolor=BG)
    print("  freeze saved", flush=True)

def render_endcard():
    fig2 = plt.figure(figsize=(12.8, 7.2), dpi=100)
    fig2.patch.set_facecolor(BG)
    def t2(x, y, s, fp=F_SANS, size=12, color=TXT, ha="center", va="center"):
        return fig2.text(x, y, s, fontproperties=fp, fontsize=size, color=color, ha=ha, va=va)
    t2(0.5, 0.84, "S C A L E   I T   U P", F_SANS, 13, DIM)
    t2(0.5, 0.74, "10,000 robots × 48 decisions/day", F_SANS_B, 30, TXT)
    # comparison bars (real numbers)
    maxw, bx = 0.42, 0.30
    jw, gw = 354.0, 1814.0
    for (yy, lab, val, col, w) in [
        (0.56, "Jev", "$354/mo", GREEN, jw / gw * maxw),
        (0.44, "GPT-4o-mini", "$1,814/mo", "#5b6470", maxw),
    ]:
        fig2.text(0.10, yy, lab, fontproperties=F_SANS_B, fontsize=16, color=TXT, ha="left", va="center")
        fig2.patches.append(Rectangle((bx, yy - 0.028), w, 0.056, transform=fig2.transFigure,
                                     facecolor=col, edgecolor="none"))
        fig2.text(bx + w + 0.02, yy, val, fontproperties=F_SANS_B, fontsize=18, color=col,
                  ha="left", va="center")
    t2(0.5, 0.30, "5.1× cheaper · p50 latency 0.53s", F_SANS_B, 22, AMBER)
    t2(0.5, 0.17, "Full breakdown: robokrunch.com", F_SANS, 18, DIM)
    fig2.savefig(f"{FRAMES_DIR}/endcard.png", dpi=100, facecolor=BG)
    plt.close(fig2)
    print("  endcard saved", flush=True)

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        render_stream(range(STREAM_FRAMES))
        render_freeze()
        render_endcard()
    elif arg == "smoke":
        for f in [0, 300, 600, 900, 1199]:
            draw_stream_frame(f)
            fig.savefig(f"/tmp/smoke_{f}.png", dpi=100, facecolor=BG)
        render_endcard()
        import shutil
        shutil.copy(f"{FRAMES_DIR}/endcard.png", "/tmp/smoke_endcard.png")
        print("smoke done")
    print("DONE")
