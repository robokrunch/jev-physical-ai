#!/usr/bin/env python3
"""Crossover analysis: Jev API vs self-hosted ModernBERT.
Reads demo-a-results.json + demo-b-results.json, prints the comparison table.
All assumptions labeled ASSUMED; everything else measured."""
import json
import math
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO_ROOT, "data")
A = json.load(open(os.path.join(DATA, "demo-a-results.json")))["aggregate"]
B = json.load(open(os.path.join(DATA, "demo-b-results.json")))

JEV_PER_M = A["cost_usd"]["per_million_decisions"]      # measured
JEV_PER_DEC = A["cost_usd"]["mean_per_decision"]        # measured
T2 = B["throughput_per_s"]                              # measured, 2-core, batch=1
MS = B["per_sample_latency_s"]["p50"] * 1000            # measured

VM_MO = 24.0          # ASSUMED: $24/mo 4-vCPU cloud VM
T4 = T2 * 2           # ASSUMED: linear scaling 2 -> 4 vCPU
CAP_MO = T4 * 86400 * 30  # decisions one VM can serve per month
DEC_PER_ROBOT_DAY = 48

print(f"Jev: ${JEV_PER_M:.2f}/M decisions (measured, {A['cost_usd']['mean_per_decision']:.2e}/decision)")
print(f"ModernBERT: {MS:.1f} ms/sample p50 on 2-core CPU (measured), {T2:.1f} samples/s")
print(f"ASSUMED: ${VM_MO:.0f}/mo 4-vCPU VM, throughput {T4:.1f}/s -> capacity {CAP_MO/1e6:.1f}M decisions/mo/VM")
print()
print(f"{'tier (decisions/mo)':>24} | {'Jev $/M':>8} | {'self-host $/M':>13} | {'VMs':>4}")
for V in (1.44e6, 14.4e6, 100e6):
    vms = max(1, math.ceil(V / CAP_MO))
    self_per_m = vms * VM_MO * 1e6 / V
    print(f"{V/1e6:>20.1f}M      | ${JEV_PER_M:>7.2f} | ${self_per_m:>12.2f} | {vms:>4}")

# crossover: single VM suffices while V* < CAP_MO
v_star = VM_MO / JEV_PER_DEC
robots = v_star / DEC_PER_ROBOT_DAY / 30
print()
print(f"Crossover (pure infra): {v_star:,.0f} decisions/mo "
      f"(= {robots:,.0f} robots @ {DEC_PER_ROBOT_DAY}/day), single VM capacity ok: {v_star < CAP_MO}")
print(f"Sensitivity: like-for-like 3-output ModernBERT ~= 3x compute (ESTIMATE) -> "
      f"crossover ~= {3*v_star:,.0f} decisions/mo")
print(f"Jev answers 3 questions/call; ModernBERT measured on 1 label only.")
