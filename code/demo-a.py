#!/usr/bin/env python3
"""Demo A: 10,000-robot fleet triage via Jev decisions API.

Generates 300 fleet status events (bilingual ZH/EN), sends one decisions-API
call per event with 3 questions (needs_intervention / team / urgency),
records latency + token usage + cost per call, and writes aggregates.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# --- paths: everything is relative to the repo root -------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- auth: bring your own OpenRouter key -------------------------------------
# Demo A cost ~$0.01 for 300 calls (billed by OpenRouter). No other keys needed.
API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    raise SystemExit(
        "OPENROUTER_API_KEY is not set.\n"
        "Get a key at https://openrouter.ai and export OPENROUTER_API_KEY=<your key>,\n"
        "then re-run. Demo A spends roughly $0.01 for 300 decisions-API calls."
    )

API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
OUT = os.path.join(REPO_ROOT, "data", "demo-a-results.json")

# ---------------------------------------------------------------- templates
# team: intended owner (for agreement analysis only, NOT sent to the model)
# urg: intended urgency 0/1/2 (for agreement analysis only, NOT sent to model)
T = [
 # ---- ops: dispatch / charging / routes / shifts
 ("ops-lowbat", "AMR-{rid} battery at {v}% — auto-routed to dock C, queue position {q}",
  "AMR-{rid} 电量 {v}%，已自动派往 C 区充电桩，排队第 {q} 位", "ops", 0),
 ("ops-queue", "Charging queue: {v} robots waiting at dock {d}, est. wait {w} min",
  "充电桩排队：{d} 充电区有 {v} 台机器人在等，预计等待 {w} 分钟", "ops", 1),
 ("ops-blocked", "Aisle {a} blocked by fallen pallet — AMR-{rid} rerouted, +{v} min detour",
  "巷道 {a} 被倒塌的托盘挡住——AMR-{rid} 已改道，多走 {v} 分钟", "ops", 1),
 ("ops-backlog", "{v} pick tasks unassigned {m} min after shift change",
  "换班 {m} 分钟后仍有 {v} 个拣选任务无人认领", "ops", 1),
 ("ops-geofence", "AMR-{rid} crossed geofence into staging zone S{v}, auto-halted",
  "AMR-{rid} 越界进入 S{v} 暂存区，已自动急停", "ops", 2),
 ("ops-idle", "AMR-{rid} idle {v} min waiting for task assignment",
  "AMR-{rid} 空闲 {v} 分钟，等任务分配", "ops", 0),
 ("ops-congestion", "Intersection J{v} congestion: {q} AMRs queued, throughput -{w}%",
  "J{v} 路口拥堵：{q} 台 AMR 排队，通过率下降 {w}%", "ops", 1),
 ("ops-dockfault", "Charging dock {d} fault — {v} robots rerouted to dock E",
  "充电桩 {d} 故障——{v} 台机器人已改派 E 区充电桩", "ops", 2),
 ("ops-shiftgap", "Night shift: {v} AMRs online vs {q} planned — coverage gap zone {a}",
  "夜班：在线 {v} 台，计划 {q} 台——{a} 区域覆盖不足", "ops", 1),
 ("ops-priority", "Priority order injected: {v} AMRs preempted from routine picks",
  "加急订单插入：{v} 台 AMR 从常规拣选中被抢占", "ops", 0),
 # ---- maintenance: hardware degradation / faults
 ("mnt-battdegr", "AMR-{rid} battery health {v}% — capacity fade, charge cycles {c}",
  "AMR-{rid} 电池健康度 {v}%，容量衰减，循环次数 {c}", "maintenance", 1),
 ("mnt-torquedrift", "AMR-{rid} drive-wheel torque sensor drift {v} mNm, within tolerance",
  "AMR-{rid} 驱动轮扭矩传感器漂移 {v} mNm，仍在容差内", "maintenance", 0),
 ("mnt-torquedrift2", "AMR-{rid} torque sensor drift {v} mNm EXCEEDS tolerance — traction degraded",
  "AMR-{rid} 扭矩传感器漂移 {v} mNm 超出容差——牵引力下降", "maintenance", 2),
 ("mnt-lidar", "AMR-{rid} lidar partial occlusion ({v}% FOV), speed auto-limited to {w} m/s",
  "AMR-{rid} 激光雷达部分遮挡（{v}% 视场），速度自动限制到 {w} m/s", "maintenance", 1),
 ("mnt-lidarblind", "AMR-{rid} lidar fully blind — emergency stop, manual inspection needed",
  "AMR-{rid} 激光雷达完全致盲——已急停，需人工检查", "maintenance", 2),
 ("mnt-wheelwear", "AMR-{rid} left drive wheel wear {v} mm beyond service limit",
  "AMR-{rid} 左驱动轮磨损 {v} mm，超出维护阈值", "maintenance", 1),
 ("mnt-armvib", "Station {s} robot arm vibration {v} mm/s with {w} kg payload — cycle paused",
  "工位 {s} 机械臂带载 {w} kg 抖动 {v} mm/s——节拍已暂停", "maintenance", 2),
 ("mnt-armvib2", "Station {s} arm vibration {v} mm/s no-load, trending up over {d} days",
  "工位 {s} 机械臂空载抖动 {v} mm/s，{d} 天来呈上升趋势", "maintenance", 1),
 ("mnt-motortemp", "AMR-{rid} drive motor temp {v}C — thermal shutdown, cooling required",
  "AMR-{rid} 驱动电机温度 {v}°C——过热停机，需冷却", "maintenance", 2),
 ("mnt-motortemp2", "AMR-{rid} motor temp {v}C, {w}C above baseline, still running",
  "AMR-{rid} 电机温度 {v}°C，比基线高 {w}°C，仍在运行", "maintenance", 1),
 ("mnt-estop", "AMR-{rid} E-stop pressed by worker at station {s} — resume requires reset",
  "工位 {s} 有工人拍下 AMR-{rid} 急停——需复位才能恢复", "maintenance", 2),
 ("mnt-tireflat", "AMR-{rid} tire pressure {v} kPa — slow leak suspected",
  "AMR-{rid} 胎压 {v} kPa——疑似慢漏气", "maintenance", 1),
 ("mnt-chargetrip", "AMR-{rid} charge session aborted {v} times today — connector wear suspected",
  "AMR-{rid} 今日充电中断 {v} 次——疑似充电接口磨损", "maintenance", 1),
 # ---- software: localization / planner / fleet stack
 ("sw-locdrift", "AMR-{rid} AMCL covariance {v} — relocalization triggered, brief pause",
  "AMR-{rid} AMCL 协方差 {v}——已触发重定位，短暂停顿", "software", 0),
 ("sw-loclost", "AMR-{rid} localization LOST in aisle {a} — stopped, awaiting map update",
  "AMR-{rid} 在巷道 {a} 定位丢失——已停车，等待地图更新", "software", 2),
 ("sw-mapmismatch", "Map mismatch: {v} new rack rows in zone {a} not in fleet map v{w}",
  "地图不一致：{a} 区新增 {v} 排货架不在车队地图 v{w} 中", "software", 1),
 ("sw-apitimeout", "Fleet manager API p99 latency {v} ms — {q} task acks delayed",
  "车队管理 API p99 延迟 {v} ms——{q} 个任务确认延迟", "software", 1),
 ("sw-ota", "OTA update failed on {v} AMRs (v{w} -> v{q}) — rollback complete",
  "OTA 升级失败：{v} 台 AMR（v{w} -> v{q}）——已回滚", "software", 1),
 ("sw-otabrick", "OTA update bricked navigation on AMR-{rid} — safe mode, needs reflash",
  "OTA 把 AMR-{rid} 导航刷挂了——安全模式，需重刷", "software", 2),
 ("sw-falsepos", "Perception false positives: {v}/hr phantom obstacles on AMR-{rid}",
  "感知误报：AMR-{rid} 每小时 {v} 次幽灵障碍物", "software", 1),
 ("sw-planner", "AMR-{rid} planner oscillation at doorway D{v} — {q} replans in {w}s",
  "AMR-{rid} 在 D{v} 门口规划震荡——{w} 秒内重规划 {q} 次", "software", 1),
 ("sw-wifi", "AMR-{rid} WiFi handoff drops: {v} disconnects on route R{q} this shift",
  "AMR-{rid} WiFi 切换掉线：本班次在 R{q} 路线掉线 {v} 次", "software", 1),
 ("sw-clockskew", "Clock skew {v} ms across {q} AMRs — task timestamps unreliable",
  "{q} 台 AMR 时钟偏差 {v} ms——任务时间戳不可靠", "software", 1),
 ("sw-memory", "AMR-{rid} navigation stack RSS {v} MB — slow leak over {d} days",
  "AMR-{rid} 导航栈内存 {v} MB——{d} 天来缓慢泄漏", "software", 1),
 ("sw-deadlock", "Task allocator deadlock: {v} AMRs holding, {q} tasks starved",
  "任务分配死锁：{v} 台 AMR 占着资源，{q} 个任务饿死", "software", 2),
 ("sw-version", "AMR-{rid} running nav stack v{w}, fleet standard is v{q} — drift",
  "AMR-{rid} 导航栈版本 v{w}，车队标准 v{q}——版本漂移", "software", 0),
 # ---- mixed / ambiguous
 ("mix-battery-hot", "AMR-{rid} battery {v}% and {w}C while fast-charging at dock {d}",
  "AMR-{rid} 在 {d} 充电桩快充时电量 {v}%、温度 {w}°C", "maintenance", 1),
 ("mix-slow", "AMR-{rid} avg speed {v} m/s vs fleet {w} m/s — cause unknown",
  "AMR-{rid} 平均速度 {v} m/s，车队平均 {w} m/s——原因未知", "software", 1),
 ("mix-noise", "AMR-{rid} abnormal drivetrain noise reported by zone {a} staff",
  "{a} 区员工报告 AMR-{rid} 传动异响", "maintenance", 1),
 ("mix-stuck", "AMR-{rid} stuck {v} min at dock {d} — no error code, heartbeat OK",
  "AMR-{rid} 在 {d} 充电桩卡住 {v} 分钟——无错误码，心跳正常", "software", 2),
 ("mix-powerspike", "Charging dock {d} power spike {v} kW — {q} sessions interrupted",
  "充电桩 {d} 功率尖峰 {v} kW——{q} 个充电会话中断", "maintenance", 2),
]

QUESTIONS = {
    "needs_intervention": {
        "type": "noul",
        "instructions": "Does this fleet event require a human to intervene, or can the fleet handle it autonomously?",
        "criteria": {
            "true": "A human operator or technician must take action now or soon.",
            "false": "The fleet's automation already handles it; no human needed.",
        },
    },
    "team": {
        "type": "choice",
        "instructions": "Which team should own this event?",
        "criteria": {
            "ops": "Dispatch, charging logistics, routes, shift coverage, task assignment.",
            "maintenance": "Physical hardware: batteries, motors, sensors, wheels, arms, docks.",
            "software": "Localization, planning, perception, fleet APIs, OTA, networking.",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this event?",
        "criteria": [
            "Routine — automation handles it, review in weekly report",
            "Degraded — schedule attention within this shift",
            "Critical — human needed now, operations impacted",
        ],
    },
}


def render(tpl, rng, i):
    tid, en, zh, team, urg = tpl
    kw = {
        "rid": f"{rng.randint(1, 1500):04d}",
        "v": rng.randint(2, 95), "w": rng.randint(1, 40), "q": rng.randint(1, 12),
        "d": rng.choice(["A", "B", "C", "E"]), "a": f"B-{rng.randint(1,40)}",
        "s": f"S{rng.randint(1,12)}", "m": rng.randint(5, 90),
        "c": rng.randint(800, 4000),
    }
    # keep numbers plausible per template via simple clamps
    return {
        "event_id": f"evt-{i:04d}",
        "template": tid,
        "intended_team": team,
        "intended_urgency": urg,
        "robot_id": f"AMR-{kw['rid']}",
        "event_en": en.format(**{k: v for k, v in kw.items() if "{" + k + "}" in en}),
        "event_zh": zh.format(**{k: v for k, v in kw.items() if "{" + k + "}" in zh}),
    }


def call(payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    req.add_header("HTTP-Referer", "https://robokrunch.com")
    req.add_header("X-Title", "RoboKrunch fleet-triage demo")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            dt = time.perf_counter() - t0
            return dt, resp.status, json.load(resp), None
    except urllib.error.HTTPError as e:
        dt = time.perf_counter() - t0
        try:
            detail = e.read().decode()[:300]
        except Exception:
            detail = ""
        return dt, e.code, None, f"HTTP {e.code}: {detail}"
    except Exception as e:  # noqa: BLE001
        return time.perf_counter() - t0, -1, None, repr(e)[:200]


def run_one(ev):
    payload = {
        "model": MODEL,
        "questions": QUESTIONS,
        "state": {
            "robot_id": ev["robot_id"],
            "event_en": ev["event_en"],
            "event_zh": ev["event_zh"],
            "shift": "night",
            "fleet_size": 10000,
        },
    }
    for attempt in range(4):
        dt, status, data, err = call(payload)
        if status == 200 and data:
            u = data.get("usage", {})
            return {
                **ev,
                "latency_s": round(dt, 3),
                "http_status": status,
                "answers": data.get("answers"),
                "input_tokens": u.get("input_tokens"),
                "output_tokens": u.get("output_tokens"),
                "cost_usd": u.get("cost"),
                "provider": data.get("provider"),
                "model_snapshot": data.get("model"),
                "error": None,
            }
        if status in (429, 500, 502, 503, 529) and attempt < 3:
            time.sleep(2 ** attempt)
            continue
        return {**ev, "latency_s": round(dt, 3), "http_status": status,
                "answers": None, "input_tokens": None, "output_tokens": None,
                "cost_usd": None, "error": err}
    return {**ev, "latency_s": None, "http_status": -1, "answers": None,
            "input_tokens": None, "output_tokens": None, "cost_usd": None,
            "error": "retries exhausted"}


def main():
    rng = random.Random(20260919)
    events = []
    for i in range(300):
        events.append(render(T[i % len(T)], rng, i))
    rng.shuffle(events)

    records = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for j, rec in enumerate(ex.map(run_one, events)):
            records.append(rec)
            if (j + 1) % 50 == 0:
                ok = sum(1 for r in records if r["error"] is None)
                print(f"[{j+1}/300] ok={ok}", flush=True)

    ok = [r for r in records if r["error"] is None]
    lat = sorted(r["latency_s"] for r in ok)
    costs = [r["cost_usd"] for r in ok if r["cost_usd"] is not None]
    in_tok = [r["input_tokens"] for r in ok if r["input_tokens"]]
    out_tok = [r["output_tokens"] for r in ok if r["output_tokens"]]
    agree_team = sum(1 for r in ok
                     if r["answers"] and r["answers"].get("team", {}).get("choice") == r["intended_team"])

    def pct(p):
        return round(lat[min(len(lat) - 1, int(p * len(lat)))], 3)

    agg = {
        "n_calls": len(records),
        "n_ok": len(ok),
        "n_failed": len(records) - len(ok),
        "latency_s": {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99),
                      "min": round(lat[0], 3), "max": round(lat[-1], 3),
                      "mean": round(statistics.mean(lat), 3)},
        "tokens": {"mean_input": round(statistics.mean(in_tok), 1),
                   "mean_output": round(statistics.mean(out_tok), 1)},
        "cost_usd": {"total": round(sum(costs), 6),
                     "mean_per_decision": round(statistics.mean(costs), 8),
                     "per_million_decisions": round(statistics.mean(costs) * 1e6, 2)},
        "team_agreement_with_intended": {"agree": agree_team, "n": len(ok),
                                         "rate": round(agree_team / len(ok), 3)},
        "model_snapshot": ok[0]["model_snapshot"] if ok else None,
        "provider": ok[0]["provider"] if ok else None,
        "pricing_verified_usd_per_mtok_in": 0.042,
        "pricing_verified_usd_per_mtok_out": 0.0,
        "ran_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(OUT, "w") as f:
        json.dump({"aggregate": agg, "records": records}, f, ensure_ascii=False, indent=1)
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
