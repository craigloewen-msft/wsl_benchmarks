#!/usr/bin/env python3
"""
RAM overhead benchmark for wslc containers.

Measures the host-side RAM cost of running an idle Alpine container by
tracking the WorkingSet64 of the ``vmmemwslc-cli-{username}`` process.

Steps:
  1. Ensure no existing wslc sessions (clean baseline).
  2. Build a minimal Alpine image.
  3. Run the container (sleep 10s) and measure vmmem RAM.
  4. Clean up and confirm RAM is released.

Uses the appropriate container binary per platform:
  - Windows: wslc
"""

import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

IMAGE_TAG = "ram-overhead-bench:latest"
CONTAINER_NAME = "ram-overhead-bench-run"
STABILIZATION_DELAY = 5   # seconds to wait after state changes
SAMPLES_PER_MEASUREMENT = 3

PLATFORM_CONFIG = {
    "Windows": {"bin": "wslc", "name": "windows"},
    "Darwin":  {"bin": "container", "name": "mac"},
    "Linux":   {"bin": "docker", "name": "linux"},
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


def bytes_to_mb(b):
    return round(b / (1024 * 1024), 2)


# ---------------------------------------------------------------------------
# RAM measurement (Windows-specific via vmmem process)
# ---------------------------------------------------------------------------

def _get_vmmem_process_name():
    """Return the expected vmmem process name for the current user."""
    username = os.getlogin()
    return f"vmmemwslc-cli-{username}"


def get_vmmem_working_set():
    """
    Return the WorkingSet64 (bytes) of the wslc vmmem process, or 0 if
    the process does not exist.

    Takes ``SAMPLES_PER_MEASUREMENT`` readings one second apart and returns
    the median to smooth transient noise.
    """
    proc_name = _get_vmmem_process_name()
    samples = []
    for _ in range(SAMPLES_PER_MEASUREMENT):
        try:
            ps_cmd = (
                f"(Get-Process -Name '{proc_name}' "
                f"-ErrorAction Stop).WorkingSet64"
            )
            out = run_capture(["powershell", "-NoProfile", "-Command", ps_cmd])
            samples.append(int(out.strip()))
        except (subprocess.CalledProcessError, ValueError):
            samples.append(0)
        if len(samples) < SAMPLES_PER_MEASUREMENT:
            time.sleep(1)

    median = int(statistics.median(samples))
    print(f"  vmmem WorkingSet64: {bytes_to_mb(median)} MB "
          f"(samples: {[bytes_to_mb(s) for s in samples]})")
    return median


def get_host_total_ram_mb():
    """Return total physical RAM on the host in MB."""
    ps_cmd = "(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize"
    out = run_capture(["powershell", "-NoProfile", "-Command", ps_cmd])
    return round(int(out.strip()) / 1024, 2)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def terminate_all_sessions(bin_name):
    """Terminate all wslc sessions so we start from a clean slate."""
    out = run_capture([bin_name, "session", "list"])
    for line in out.strip().splitlines()[1:]:   # skip header
        parts = line.split()
        if parts:
            session_id = parts[0]
            print(f"  Terminating session {session_id}")
            run([bin_name, "session", "terminate", session_id],
                check=False, quiet=True)


def wait_for_vmmem_gone(timeout=30):
    """Wait until the vmmem process disappears."""
    proc_name = _get_vmmem_process_name()
    print(f"  Waiting for {proc_name} to exit ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            run_capture(["powershell", "-NoProfile", "-Command",
                         f"Get-Process -Name '{proc_name}' -ErrorAction Stop"])
            time.sleep(2)
        except subprocess.CalledProcessError:
            print(f"  {proc_name} is gone.")
            return
    print(f"  Warning: {proc_name} still present after {timeout}s")


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def main():
    bin_name = get_container_bin()
    plat = get_platform_name()
    today = date.today().isoformat()
    script_dir = Path(__file__).resolve().parent
    output_file = script_dir / f"{plat}-ram-overhead-{today}.json"
    vmmem_name = _get_vmmem_process_name()

    host_total_mb = get_host_total_ram_mb()
    print(f"Platform: {plat} | Binary: {bin_name}")
    print(f"Host RAM: {host_total_mb} MB")
    print(f"vmmem process: {vmmem_name}")
    print()

    try:
        # --- Step 1: Clean slate ----------------------------------------
        print("=== Step 1: Ensuring clean slate (no active sessions) ===")
        run([bin_name, "rm", "-f", CONTAINER_NAME], check=False, quiet=True)
        terminate_all_sessions(bin_name)
        wait_for_vmmem_gone()
        print()

        # --- Step 2: Build image ----------------------------------------
        print("=== Step 2: Building container image ===")
        run([bin_name, "build", "-t", IMAGE_TAG, str(script_dir)])
        # Building may start a session; terminate it to reset baseline.
        terminate_all_sessions(bin_name)
        wait_for_vmmem_gone()
        print()

        # --- Step 3: Run container and measure --------------------------
        print("=== Step 3: Running idle container ===")
        run([bin_name, "run", "-d", "--name", CONTAINER_NAME,
             IMAGE_TAG, "sleep", "10"])
        print(f"  Waiting {STABILIZATION_DELAY}s for VM to stabilize ...")
        time.sleep(STABILIZATION_DELAY)

        container_ws = get_vmmem_working_set()
        container_mb = bytes_to_mb(container_ws)
        print(f"  → Container RAM overhead: {container_mb} MB\n")

        # --- Step 4: Cleanup --------------------------------------------
        print("=== Step 4: Cleaning up ===")
        run([bin_name, "rm", "-f", CONTAINER_NAME])
        run([bin_name, "rmi", IMAGE_TAG], check=False)
        terminate_all_sessions(bin_name)
        print(f"  Waiting {STABILIZATION_DELAY}s for cleanup ...")
        time.sleep(STABILIZATION_DELAY)

        post_cleanup_ws = get_vmmem_working_set()
        post_cleanup_mb = bytes_to_mb(post_cleanup_ws)
        print(f"  → Post-cleanup vmmem: {post_cleanup_mb} MB\n")

        # --- Results ----------------------------------------------------
        results = {
            "platform": plat,
            "date": today,
            "container_tool": bin_name,
            "host_total_ram_mb": host_total_mb,
            "vmmem_process": vmmem_name,
            "ram_overhead_mb": {
                "idle_container_mb": container_mb,
                "post_cleanup_mb": post_cleanup_mb,
            },
            "stabilization_delay_seconds": STABILIZATION_DELAY,
            "samples_per_measurement": SAMPLES_PER_MEASUREMENT,
        }

        output_file.write_text(json.dumps(results, indent=2) + "\n")
        print_success(output_file, results)

    finally:
        run([bin_name, "rm", "-f", CONTAINER_NAME], check=False, quiet=True)


def print_success(output_file, results):
    print()
    print("=" * 50)
    print("  Benchmark completed successfully!")
    print(f"  Results written to {output_file}")
    print("=" * 50)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
