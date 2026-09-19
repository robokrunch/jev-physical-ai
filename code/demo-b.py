#!/usr/bin/env python3
"""Demo B: Jev vs self-hosted ModernBERT-base on a $0 box.

Method (documented, honest): ModernBERT-base as a frozen encoder, mean-pooled
embeddings, nearest-centroid classifier over 18 hand-labeled exemplars
(6 per team class). Test on 100 fleet events reused from Demo A; agreement is
measured against Jev's team choice and labeled as AGREEMENT, not accuracy.
Per-sample latency measured on 2-core CPU, batch size 1, torch single... default threads.
"""
from __future__ import annotations

import json
import os
import time

import torch
from transformers import AutoModel, AutoTokenizer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")

OUT = os.environ.get("DEMO_B_OUT", os.path.join(DATA_DIR, "demo-b-results.json"))
A_PATH = os.environ.get("DEMO_A_IN", os.path.join(DATA_DIR, "demo-a-results.json"))
# HuggingFace hub id — transformers downloads it automatically (~598 MB, one-time).
# Point at a local snapshot with MODERNBERT_MODEL_ID=/path/to/ModernBERT-base if you have one.
MODEL_ID = os.environ.get("MODERNBERT_MODEL_ID", "answerdotai/ModernBERT-base")
CLASSES = ["ops", "maintenance", "software"]

# exemplar templates: 6 per class, instantiated once each (fixed values)
EXEMPLARS = {
    "ops": [
        "AMR-0007 battery at 22% — auto-routed to dock C, queue position 3",
        "Charging queue: 6 robots waiting at dock C, est. wait 18 min",
        "Aisle B-14 blocked by fallen pallet — AMR-0231 rerouted, +9 min detour",
        "AMR-1102 idle 25 min waiting for task assignment",
        "Intersection J3 congestion: 8 AMRs queued, throughput -30%",
        "Night shift: 41 AMRs online vs 52 planned — coverage gap zone B-22",
    ],
    "maintenance": [
        "AMR-0455 battery health 71% — capacity fade, charge cycles 2310",
        "AMR-0091 lidar partial occlusion (35% FOV), speed auto-limited to 0.8 m/s",
        "AMR-0091 lidar fully blind — emergency stop, manual inspection needed",
        "AMR-0777 drive motor temp 94C — thermal shutdown, cooling required",
        "Station S4 robot arm vibration 3.2 mm/s with 12 kg payload — cycle paused",
        "AMR-0330 tire pressure 180 kPa — slow leak suspected",
    ],
    "software": [
        "AMR-1204 AMCL covariance 0.42 — relocalization triggered, brief pause",
        "AMR-1204 localization LOST in aisle B-9 — stopped, awaiting map update",
        "Fleet manager API p99 latency 840 ms — 5 task acks delayed",
        "OTA update failed on 14 AMRs (v3.2 -> v3.3) — rollback complete",
        "Perception false positives: 23/hr phantom obstacles on AMR-0567",
        "Task allocator deadlock: 6 AMRs holding, 19 tasks starved",
    ],
}


def encode(texts, tok, model):
    enc = tok(texts, padding=True, truncation=True, max_length=128, return_tensors="pt")
    with torch.no_grad():
        out = model(**enc).last_hidden_state
    mask = enc["attention_mask"].unsqueeze(-1).float()
    emb = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-6)
    return torch.nn.functional.normalize(emb, dim=1)


def main():
    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID).eval()
    load_s = time.perf_counter() - t0
    params = sum(p.numel() for p in model.parameters())
    threads = torch.get_num_threads()

    centroids = {}
    for cls in CLASSES:
        centroids[cls] = encode(EXEMPLARS[cls], tok, model).mean(0)

    with open(A_PATH) as f:
        records = json.load(f)["records"]
    ok = [r for r in records if r["error"] is None][:100]

    # warmup
    encode(["warmup one", "warmup two"], tok, model)

    per_sample, preds = [], []
    for r in ok:
        t1 = time.perf_counter()
        e = encode([r["event_en"]], tok, model)[0]
        sims = {c: float(torch.dot(e, centroids[c])) for c in CLASSES}
        pred = max(sims, key=sims.get)
        per_sample.append(time.perf_counter() - t1)
        jev_team = r["answers"]["team"]["choice"] if r["answers"] else None
        preds.append({"event_id": r["event_id"], "pred": pred,
                      "jev_team": jev_team, "agree": pred == jev_team})

    agree = sum(1 for p in preds if p["agree"])
    per_sample.sort()
    res = {
        "model": MODEL_ID,
        "params": params,
        "torch_threads": threads,
        "device": "cpu",
        "vm": "2-core AMD EPYC, 7.7GB RAM",
        "method": "frozen ModernBERT-base encoder, mean pooling, L2-normalized nearest centroid; 18 hand-labeled exemplars (6/class); batch size 1",
        "model_load_s": round(load_s, 2),
        "n_exemplars_labeled": 18,
        "n_test": len(ok),
        "per_sample_latency_s": {
            "p50": round(per_sample[len(per_sample)//2], 4),
            "mean": round(sum(per_sample)/len(per_sample), 4),
            "min": round(per_sample[0], 4),
            "max": round(per_sample[-1], 4),
        },
        "throughput_per_s": round(len(ok) / sum(per_sample), 2),
        "agreement_with_jev_team": {"agree": agree, "n": len(ok),
                                    "rate": round(agree/len(ok), 3),
                                    "note": "agreement with Jev's choice, NOT accuracy vs ground truth"},
        "generalization_note": "exemplars drawn from 18 templates; test events span all 41 templates incl. held-out phrasing",
        "ran_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "predictions": preds,
    }
    with open(OUT, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "predictions"}, indent=2))


if __name__ == "__main__":
    main()
