# Reproducing the Jev × Physical AI demos

Everything in this repo was measured on 2026-09-19. All quotable numbers are
either measured (see `data/`) or explicitly labeled as assumptions. Re-running
these scripts lets you verify the numbers yourself.

## Layout

```
code/            demo scripts (runnable)
data/            measured results (aggregate + per-call records)
assets/          charts + the 60-second demo video
REPRODUCE.md     this file
```

## What you need

- Python 3.11+
- Demo A only: an **OpenRouter API key** (`https://openrouter.ai`). Demo A makes
  300 calls to `typesafe/jev-1.13` and spends roughly **$0.01** total.
- Demo B only: `torch` + `transformers` (`pip install torch transformers`);
  ModernBERT-base (~598 MB) downloads automatically from HuggingFace on first run.
- Charts/video: `pip install matplotlib numpy` (video render also needs `ffmpeg`).

## Demo A — fleet triage (flagship)

300 simulated bilingual (ZH/EN) warehouse-AMR events, one OpenRouter decisions-API
call per event, 3 questions each (`needs_intervention` / `team` / `urgency`).
Writes per-call latency, token usage, and billed cost to `data/demo-a-results.json`
and prints the aggregate.

```bash
export OPENROUTER_API_KEY=<your key>
python3 code/demo-a.py          # ~10 minutes, 6-way concurrent, ~$0.01
```

Expected (from our 2026-09-19 run): 300/300 OK, latency p50 ≈ 0.53 s / p95 ≈
0.81 s, mean cost ≈ $0.0000246/decision, **$24.57 per 1M decisions**.
The billed `cost` field cross-checks exactly against 584.9 mean input tokens ×
$0.042/MTok with $0 output-token pricing.

Your numbers will move: OpenRouter latency depends on your network route, and
TypeSafe pricing may change. The per-call records in `data/` record the model
snapshot (`typesafe/jev-1.13-20260917`) and provider (`TypeSafe`) we measured.

## Demo B — Jev vs self-hosted ModernBERT (skeptic demo)

Frozen `answerdotai/ModernBERT-base` encoder, mean pooling, nearest-centroid
classifier over 18 hand-labeled exemplars (6 per team class), tested on 100 events
reused from Demo A's output. Measures per-sample latency on CPU and agreement
with Jev's team choice. No API calls; runs on your machine.

```bash
python3 code/demo-b.py          # CPU-only; ~5 minutes on a 2-core box
```

Our run (2-core AMD EPYC, CPU-only, batch=1): p50 **169.3 ms**/sample,
5.06 samples/s, agreement with Jev's team choice 66/100. Note the comparison is
deliberately asymmetric: Jev answers **3 questions per call**, ModernBERT was
measured on **1 label** — the repo README explains the crossover math and its
assumptions (labeled as such).

## Charts and crossover math

```bash
python3 code/charts.py      # regenerates assets/chart-fleet-cost.png + chart-latency.png
python3 code/crossover.py   # prints the Jev-vs-self-host cost table + crossover analysis
```

`charts.py` labels every assumption inline (GPT-4o-mini token assumptions,
ModernBERT VM-cost assumptions). The crossover analysis: self-hosting wins on
pure infra cost above ≈977K decisions/month (≈678 robots at 48 decisions/day)
under those labeled assumptions; below that, the API is cheaper *and* you skip
labeling and ops.

## Video

`assets/fleet-triage-demo.mp4` (60 s, 1280×720) was rendered from the real
`demo-a-results.json` records — the cost ticker you see is the actual billed
cost per call. To re-render from your own run:

```bash
python3 code/render_video.py        # writes 1200 PNG frames to ./frames/
# example: 50 s stream (1200 frames @24fps) + freeze hold + endcard → 60 s total
ffmpeg -framerate 24 -i frames/stream_%04d.png -i frames/freeze.png -i frames/endcard.png \
  -filter_complex "[1:v]tpad=stop=168:stop_mode=clone[v1];[v1][2:v]concat=n=2:v=1" \
  -c:v libx264 -pix_fmt yuv420p -crf 20 assets/fleet-triage-demo.mp4
```

The renderer's `smoke` mode (`python3 code/render_video.py smoke`) writes a few
sample frames to `/tmp/` for a quick visual check. Frame rendering needs the
`DejaVu Sans` / `Noto Sans SC` fonts for the bilingual feed.

## What we did NOT verify (fact boundaries)

These hold for our published numbers and for anything you re-run here:

- **Simulated events.** The fleet incidents are synthetic templates (41 of them),
  not real warehouse telemetry. The 300 API calls, latencies, and bills are real
  measurements; the underlying "robots" are not.
- **No real robot hardware or edge NPU.** Demo B ran on datacenter CPU, not an
  edge device. No dev boards on hand at measurement time.
- **Not TypeSafe's native `/v1/systemone` protocol.** OpenRouter exposes only the
  decisions Q&A API for `typesafe/jev-1.13`. The agentic `/v1/systemone` endpoint
  (used by the jev-ultrafast repo) was not measured here.
- **No soak test.** 300 calls in one session; no week-long reliability run.
- **No probability calibration.** Jev returns probabilities/confidence; we did
  not measure whether "0.8" means 80%.
- **GPT-4o-mini cost comparison is assumed, not measured.** We did not run the
  triage on 4o-mini (would need prompt engineering + more spend); the $1,814/mo
  figure follows from labeled token assumptions.

If you publish re-runs, keep these caveats attached to the numbers.
