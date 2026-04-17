#!/usr/bin/env python3
"""
Run every container benchmark with a TUI progress ribbon.

Displays a coloured status ribbon pinned to the top of the terminal
(benchmark name + progress) with scrolling output beneath it.  Prints
a pass / fail summary at the end.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

# ── Benchmark registry (directory name → display label) ──────────────────

BENCHMARKS = [
    ("startup-time",  "Cold Start Timing"),
    ("cpu-test",      "CPU Stress (pts/smallpt)"),
    ("disk-space",    "Disk Space (kernel compile)"),
    ("file-perf",     "File I/O Performance"),
    ("network-speed", "Network Speed (iperf3)"),
    ("ram-overhead",  "RAM Overhead"),
]

# ── ANSI escape helpers ──────────────────────────────────────────────────

CSI       = "\033["
RESET     = f"{CSI}0m"
BOLD      = f"{CSI}1m"
BG_BLUE   = f"{CSI}44m"
BG_GREEN  = f"{CSI}42m"
BG_RED    = f"{CSI}41m"
BG_YELLOW = f"{CSI}43m"
FG_WHITE  = f"{CSI}97m"
FG_BLACK  = f"{CSI}30m"
CLEAR_SCR = f"{CSI}2J"
SAVE_CUR  = f"{CSI}s"
REST_CUR  = f"{CSI}u"
HIDE_CUR  = f"{CSI}?25l"
SHOW_CUR  = f"{CSI}?25h"

RIBBON_ROWS = 2  # ribbon + separator


def _pos(row, col=1):
    return f"{CSI}{row};{col}H"


def _scroll_region(top, bottom):
    return f"{CSI}{top};{bottom}r"


def _enable_vt():
    """Enable virtual-terminal (ANSI) processing on Windows 10+."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        k32.GetConsoleMode(h, ctypes.byref(mode))
        k32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass  # best-effort


# ── Ribbon ───────────────────────────────────────────────────────────────

def _draw_ribbon(idx, total, name, status="RUNNING"):
    """Redraw the two-line ribbon at the bottom without disturbing scroll."""
    rows = os.get_terminal_size().lines
    cols = os.get_terminal_size().columns

    bg = {
        "RUNNING":  BG_BLUE,
        "PASSED":   BG_GREEN,
        "FAILED":   BG_RED,
        "ERROR":    BG_RED,
        "ABORTED":  BG_YELLOW,
    }.get(status.split()[0], BG_BLUE)

    left = f"  [{idx}/{total}]  {name}  "
    right = f"  {status}  "
    pad = max(cols - len(left) - len(right), 0)
    ribbon_text = (left + " " * pad + right)[:cols]

    sep_row = rows - 1
    ribbon_row = rows

    sys.stdout.write(
        SAVE_CUR
        + _pos(sep_row) + f"{BOLD}{'─' * cols}{RESET}"
        + _pos(ribbon_row) + f"{bg}{FG_WHITE}{BOLD}{ribbon_text}{RESET}"
        + REST_CUR
    )
    sys.stdout.flush()


# ── Terminal state management ────────────────────────────────────────────

def _setup_screen(idx, total, name):
    """Clear screen, draw ribbon at bottom, and confine scrolling above."""
    rows = os.get_terminal_size().lines
    sys.stdout.write(CLEAR_SCR + _pos(1) + HIDE_CUR)
    sys.stdout.flush()

    _draw_ribbon(idx, total, name)

    # Scroll region: line 1 up to just above the separator
    sys.stdout.write(_scroll_region(1, rows - RIBBON_ROWS))
    sys.stdout.write(_pos(1))
    sys.stdout.flush()


def _reset_terminal():
    """Restore full-screen scroll region and cursor visibility."""
    rows = os.get_terminal_size().lines
    sys.stdout.write(
        _scroll_region(1, rows) + SHOW_CUR + CLEAR_SCR + _pos(1)
    )
    sys.stdout.flush()


# ── Summary ──────────────────────────────────────────────────────────────

def _print_summary(results, total):
    passed  = [r for r in results if r[1] == "PASSED"]
    failed  = [r for r in results if r[1] in ("FAILED", "ERROR", "ABORTED")]
    skipped = [r for r in results if r[1] == "SKIP"]

    cols = os.get_terminal_size().columns
    bar = "=" * cols

    print(f"{BOLD}{bar}{RESET}")
    print(f"{BOLD}  All Benchmarks Complete  —  "
          f"{len(passed)}/{total} passed{RESET}")
    print(f"{BOLD}{bar}{RESET}")
    print()

    for name, status, detail in results:
        if status == "PASSED":
            tag = f"{BG_GREEN}{FG_WHITE}{BOLD} PASS {RESET}"
            print(f"  {tag}  {name}")
        elif status == "SKIP":
            tag = f"{BG_YELLOW}{FG_BLACK}{BOLD} SKIP {RESET}"
            print(f"  {tag}  {name}  ({detail})")
        else:
            tag = f"{BG_RED}{FG_WHITE}{BOLD} FAIL {RESET}"
            print(f"  {tag}  {name}  ({detail})")

    print()
    if failed:
        print(f"{BG_RED}{FG_WHITE}{BOLD}"
              f"  RESULT: FAILURE — {len(failed)} benchmark(s) failed  "
              f"{RESET}")
    else:
        print(f"{BG_GREEN}{FG_WHITE}{BOLD}"
              f"  RESULT: SUCCESS — all benchmarks passed!  "
              f"{RESET}")
    print()


# ── Main loop ────────────────────────────────────────────────────────────

def main():
    _enable_vt()
    script_dir = Path(__file__).resolve().parent
    total = len(BENCHMARKS)
    results = []

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"

    try:
        for idx, (bench_dir, bench_name) in enumerate(BENCHMARKS, 1):
            bench_script = script_dir / bench_dir / "run-benchmark.py"

            if not bench_script.exists():
                results.append((bench_name, "SKIP", "script not found"))
                continue

            _setup_screen(idx, total, bench_name)

            proc = None
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-u", str(bench_script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )

                for line in proc.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()

                proc.wait()

                if proc.returncode == 0:
                    results.append((bench_name, "PASSED", None))
                    _draw_ribbon(idx, total, bench_name, "PASSED ✓")
                else:
                    results.append((bench_name, "FAILED",
                                    f"exit code {proc.returncode}"))
                    _draw_ribbon(idx, total, bench_name, "FAILED ✗")

            except KeyboardInterrupt:
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc.wait()
                results.append((bench_name, "ABORTED", "interrupted by user"))
                raise

            except Exception as exc:
                results.append((bench_name, "ERROR", str(exc)))
                _draw_ribbon(idx, total, bench_name, "ERROR ✗")

            # Brief pause so the user can see the final ribbon status
            if idx < total:
                time.sleep(2)

    except KeyboardInterrupt:
        pass  # fall through to summary
    finally:
        _reset_terminal()

    _print_summary(results, total)

    if any(r[1] in ("FAILED", "ERROR", "ABORTED") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
