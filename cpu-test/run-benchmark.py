#!/usr/bin/env python3
"""
CPU stress benchmark for container technology.

Runs the Phoronix Test Suite smallpt ray-tracing benchmark inside a
container and records the average completion time.

Uses the appropriate container binary per platform:
  - Windows: docker
  - Mac:     container
  - Linux:   docker
"""

import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

IMAGE_TAG = "cpu-stress-bench:latest"
CONTAINER_NAME = "cpu-stress-bench-run"
TEST_RUNS = 3

PLATFORM_CONFIG = {
    "Windows": {"bin": "docker", "name": "windows"},
    "Darwin": {"bin": "container", "name": "mac"},
    "Linux": {"bin": "docker", "name": "linux"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd, check=True, quiet=False):
    """Run a command, streaming output to the console."""
    if not quiet:
        print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check, capture_output=quiet)
    return result.returncode


def run_capture(cmd):
    """Run a command and return its stdout."""
    return subprocess.run(
        cmd, check=True, capture_output=True, text=True,
    ).stdout


def get_container_bin():
    system = platform.system()
    config = PLATFORM_CONFIG.get(system)
    if not config:
        sys.exit(f"Unsupported platform: {system}")
    bin_name = config["bin"]
    if not shutil.which(bin_name):
        sys.exit(f"Container binary '{bin_name}' not found in PATH")
    return bin_name


def get_platform_name():
    return PLATFORM_CONFIG[platform.system()]["name"]


def parse_average(output):
    """
    Parse the 'Average:' line from phoronix grep output.

    Expected format from:
      ... | grep -A 1 "Average:"
    is something like:
      Average: 123.45 Seconds
    """
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Average:"):
            match = re.match(r"Average:\s+([\d.]+)\s+(.*)", line)
            if match:
                return float(match.group(1)), match.group(2).strip()
    return None, None


def print_success(output_file, results):
    print()
    print("=" * 50)
    print("  Benchmark completed successfully!")
    print(f"  Results written to {output_file}")
    print("=" * 50)
    print(json.dumps(results, indent=2))


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def main():
    bin_name = get_container_bin()
    plat = get_platform_name()
    today = date.today().isoformat()
    script_dir = Path(__file__).resolve().parent
    output_file = script_dir / f"{plat}-cpu-stress-{today}.json"

    print(f"Platform: {plat} | Binary: {bin_name}")
    print(f"Benchmark: pts/smallpt (ray tracing)")
    print(f"Test runs: {TEST_RUNS}")
    print()

    run([bin_name, "rm", "-f", CONTAINER_NAME], check=False, quiet=True)

    try:
        # --- Step 1: Build the container image ----------------------------
        print("=== Step 1: Building container image ===")
        run([bin_name, "build", "-t", IMAGE_TAG, str(script_dir)])
        print()

        # --- Step 2: Run the benchmark ------------------------------------
        print("=== Step 2: Running CPU stress benchmark (pts/smallpt) ===")
        print("  This may take several minutes ...\n")
        bench_cmd = (
            "printf 'y\\nn\\nn\\nn\\nn\\nn\\ny\\n' "
            "| ./phoronix-test-suite batch-setup > /dev/null 2>&1 && "
            "PTS_SILENT_MODE=1 "
            "TEST_RESULTS_NAME=smallpt "
            "TEST_RESULTS_IDENTIFIER=ci "
            f"TEST_RUNS={TEST_RUNS} "
            "./phoronix-test-suite batch-benchmark pts/smallpt"
        )
        cmd = [
            bin_name, "run", "--name", CONTAINER_NAME,
            IMAGE_TAG, "/bin/bash", "-c", bench_cmd,
        ]
        print(f"  $ {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"  stdout: {result.stdout[-500:]}")
            print(f"  stderr: {result.stderr[-500:]}")
            sys.exit(f"Benchmark failed with exit code {result.returncode}")

        output = result.stdout
        print(f"  Raw output:\n{output}")

        average_value, average_unit = parse_average(output)
        if average_value is None:
            sys.exit(f"Could not parse Average from output:\n{output}")

        print(f"  → Average: {average_value} {average_unit}\n")

        # --- Step 3: Cleanup ----------------------------------------------
        print("=== Step 3: Cleaning up ===")
        run([bin_name, "rm", "-f", CONTAINER_NAME])
        # Remove image if supported (e.g. docker rmi); not all tools have this.
        run([bin_name, "rmi", IMAGE_TAG], check=False, quiet=True)
        print()

        # --- Results ------------------------------------------------------
        results = {
            "platform": plat,
            "date": today,
            "container_tool": bin_name,
            "benchmark": "pts/smallpt",
            "test_runs": TEST_RUNS,
            "cpu_benchmark": {
                "average_value": average_value,
                "unit": average_unit,
            },
        }

        output_file.write_text(json.dumps(results, indent=2) + "\n")
        print_success(output_file, results)

    finally:
        run([bin_name, "rm", "-f", CONTAINER_NAME], check=False, quiet=True)
        run([bin_name, "rmi", IMAGE_TAG], check=False, quiet=True)


if __name__ == "__main__":
    main()
