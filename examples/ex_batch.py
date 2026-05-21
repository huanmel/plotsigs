"""
examples/ex_batch.py
=====================
Batch runner — regenerate all example output files in sequence.

Runs each example as a subprocess with show=False (file-save only), collects
pass/fail results, and prints a summary.  Useful for CI or after changing the
library to verify all examples still produce output.

Usage:
    python examples/ex_batch.py
    python examples/ex_batch.py --stop-on-fail   # abort after first failure

Run from repo root.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

EXAMPLES = [
    "examples/ex_plot_from_script.py",
    "examples/ex_plot_from_csv.py",
    "examples/ex_plot_control_transient.py",
    "examples/ex_plot_csv_analysis.py",
    "examples/ex_plot_csv_analysis_sim.py",
    "examples/ex_real_log_analysis.py",
    "examples/ex_multi_log_analysis.py",
    "examples/ex_template_function.py",
    "examples/ex_compare_naive_correct.py",
    "examples/ex_enum_phases.py",
    "examples/ex_quickplot.py",
]

parser = argparse.ArgumentParser(description="Regenerate all plotsigs example outputs.")
parser.add_argument("--stop-on-fail", action="store_true",
                    help="Abort immediately after the first failure.")
args = parser.parse_args()

ok: list[str]     = []
failed: list[str] = []

for script in EXAMPLES:
    label = Path(script).stem
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True,
        env={**__import__("os").environ, "MPLBACKEND": "Agg"},  # non-interactive
    )
    elapsed = time.perf_counter() - t0

    if result.returncode == 0:
        ok.append(label)
        print(f"  OK  {label:<45} ({elapsed:.1f}s)")
    else:
        failed.append(label)
        print(f"FAIL  {label:<45} ({elapsed:.1f}s)")
        for line in result.stderr.strip().splitlines()[-8:]:
            print(f"      {line}")
        if args.stop_on_fail:
            print("\nStopped after first failure (--stop-on-fail).")
            sys.exit(1)

total = len(EXAMPLES)
print(f"\n{len(ok)}/{total} examples succeeded.")
if failed:
    print("Failed:", ", ".join(failed))
    sys.exit(1)
