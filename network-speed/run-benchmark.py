#!/usr/bin/env python3
"""
Network speed benchmark for container technology.

Measures TCP throughput (upload and download) between the host and a
container using iperf3. The iperf3 server runs inside the container
and the iperf3 client runs on the host.

Modes:
  default:  Uses Docker (or platform-equivalent) containers.
  --wsl:    Uses the default WSL distro instead of a container.
            Requires iperf3 installed in the WSL distro.

Uses the appropriate container binary per platform:
  - Windows: docker
  - Mac:     container
  - Linux:   docker
"""

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

IMAGE_TAG = "network-speed-bench:latest"
CONTAINER_NAME = "network-speed-bench-run"
IPERF3_PORT = 5201
TEST_DURATION = 10  # seconds per direction

PLATFORM_CONFIG = {
    "Windows": {"bin": "docker", "name": "windows"},
    "Darwin": {"bin": "container", "name": "mac"},
    "Linux": {"bin": "docker", "name": "linux"},
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def run(cmd, check=True, quiet=False):
    """Run a command, streaming output to the console."""
    if not quiet:
        print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check, capture_output=quiet)
    return result.returncode


def wait_for_iperf3(host, port=IPERF3_PORT, timeout=30):
    """Wait until the iperf3 server is accepting connections."""
    print(f"  Waiting for iperf3 server on {host}:{port} ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print("  iperf3 server is ready.")
                return
        except OSError:
            time.sleep(1)
    sys.exit(f"iperf3 server did not start within {timeout}s")


def run_iperf3_client(host, direction="upload", duration=TEST_DURATION):
    """
    Run iperf3 client on the host and return parsed JSON results.

    direction: "upload"   = client sends to server (host -> target)
               "download" = server sends to client (target -> host, -R flag)
    """
    cmd = [
        "iperf3", "-c", host,
        "-p", str(IPERF3_PORT),
        "-t", str(duration),
        "--json",
    ]
    if direction == "download":
        cmd.append("-R")

    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def bits_to_MBps(bits_per_second):
    """Convert bits/s to megabytes/s (MB/s)."""
    return round(bits_per_second / 8 / 1_000_000, 2)


def print_success(output_file, results):
    print()
    print("=" * 50)
    print("  Benchmark completed successfully!")
    print(f"  Results written to {output_file}")
    print("=" * 50)
    print(json.dumps(results, indent=2))


# ---------------------------------------------------------------------------
# Docker (container) mode
# ---------------------------------------------------------------------------

def get_container_bin():
    system = platform.system()
    config = PLATFORM_CONFIG.get(system)
    if not config:
        sys.exit(f"Unsupported platform: {system}")
    bin_name = config["bin"]
    if not shutil.which(bin_name):
        sys.exit(f"Container binary '{bin_name}' not found in PATH")
    return bin_name


def run_docker_benchmark(plat, today, script_dir):
    bin_name = get_container_bin()
    output_file = script_dir / f"{plat}-network-speed-{today}.json"

    print(f"Platform: {plat} | Binary: {bin_name}")
    print(f"Test duration: {TEST_DURATION}s per direction")
    print()

    run([bin_name, "rm", "-f", CONTAINER_NAME], check=False, quiet=True)

    try:
        print("=== Step 1: Building container image ===")
        run([bin_name, "build", "-t", IMAGE_TAG, str(script_dir)])
        print()

        print("=== Step 2: Starting iperf3 server in container ===")
        run([bin_name, "run", "-d", "--name", CONTAINER_NAME,
             "-p", f"{IPERF3_PORT}:{IPERF3_PORT}", IMAGE_TAG])
        wait_for_iperf3("127.0.0.1")
        print()

        print("=== Step 3: Measuring upload (host -> container) ===")
        upload_result = run_iperf3_client("127.0.0.1", "upload")
        upload_bps = upload_result["end"]["sum_received"]["bits_per_second"]
        print(f"  Upload: {bits_to_MBps(upload_bps)} MB/s\n")

        print("=== Step 4: Measuring download (container -> host) ===")
        download_result = run_iperf3_client("127.0.0.1", "download")
        download_bps = download_result["end"]["sum_received"]["bits_per_second"]
        print(f"  Download: {bits_to_MBps(download_bps)} MB/s\n")

        print("=== Step 5: Cleaning up ===")
        run([bin_name, "rm", "-f", CONTAINER_NAME])
        run([bin_name, "rmi", IMAGE_TAG], check=False)
        print()

        results = {
            "platform": plat,
            "date": today,
            "container_tool": bin_name,
            "network_speed_MBps": {
                "upload_to_container": bits_to_MBps(upload_bps),
                "download_from_container": bits_to_MBps(download_bps),
            },
            "test_duration_seconds": TEST_DURATION,
        }

        output_file.write_text(json.dumps(results, indent=2) + "\n")
        print_success(output_file, results)

    finally:
        run([bin_name, "rm", "-f", CONTAINER_NAME], check=False, quiet=True)
        run([bin_name, "rmi", IMAGE_TAG], check=False, quiet=True)


# ---------------------------------------------------------------------------
# WSL mode
# ---------------------------------------------------------------------------

def get_wsl_ip():
    """Get the IP address of the default WSL distro."""
    result = subprocess.run(
        ["wsl", "--", "ip", "-4", "-o", "addr", "show", "eth0"],
        check=True, capture_output=True, text=True,
    )
    # Output like: "2: eth0  inet 172.28.169.147/20 ..."
    for token in result.stdout.split():
        if "/" in token and token[0].isdigit():
            return token.split("/")[0]
    sys.exit("Could not determine WSL IP address")


def run_wsl_benchmark(plat, today, script_dir):
    output_file = script_dir / f"{plat}-network-speed-wsl-{today}.json"

    if not shutil.which("wsl"):
        sys.exit("wsl is not available on this system")

    # Verify iperf3 is installed in WSL
    rc = subprocess.run(
        ["wsl", "--", "which", "iperf3"],
        capture_output=True,
    ).returncode
    if rc != 0:
        sys.exit("iperf3 is not installed in the default WSL distro. "
                 "Install it with: wsl -- sudo apt install iperf3")

    wsl_ip = get_wsl_ip()

    print(f"Platform: {plat} | Mode: WSL")
    print(f"WSL IP: {wsl_ip}")
    print(f"Test duration: {TEST_DURATION}s per direction")
    print()

    wsl_server = None
    try:
        print("=== Step 1: Starting iperf3 server in WSL ===")
        wsl_server = subprocess.Popen(
            ["wsl", "--", "iperf3", "-s", "-p", str(IPERF3_PORT)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        time.sleep(1)
        if wsl_server.poll() is not None:
            stderr = wsl_server.stderr.read().decode(errors="replace")
            sys.exit(f"iperf3 server in WSL failed to start: {stderr}")
        wait_for_iperf3(wsl_ip)
        print()

        print("=== Step 2: Measuring upload (host -> WSL) ===")
        upload_result = run_iperf3_client(wsl_ip, "upload")
        upload_bps = upload_result["end"]["sum_received"]["bits_per_second"]
        print(f"  Upload: {bits_to_MBps(upload_bps)} MB/s\n")

        print("=== Step 3: Measuring download (WSL -> host) ===")
        download_result = run_iperf3_client(wsl_ip, "download")
        download_bps = download_result["end"]["sum_received"]["bits_per_second"]
        print(f"  Download: {bits_to_MBps(download_bps)} MB/s\n")

        print("=== Step 4: Stopping iperf3 server ===")
        wsl_server.terminate()
        wsl_server.wait(timeout=5)
        wsl_server = None
        print()

        results = {
            "platform": plat,
            "date": today,
            "container_tool": "wsl",
            "wsl_ip": wsl_ip,
            "network_speed_MBps": {
                "upload_to_wsl": bits_to_MBps(upload_bps),
                "download_from_wsl": bits_to_MBps(download_bps),
            },
            "test_duration_seconds": TEST_DURATION,
        }

        output_file.write_text(json.dumps(results, indent=2) + "\n")
        print_success(output_file, results)

    finally:
        if wsl_server and wsl_server.poll() is None:
            wsl_server.terminate()
            try:
                wsl_server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                wsl_server.kill()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Network speed benchmark (host <-> container/WSL)")
    parser.add_argument(
        "--wsl", action="store_true",
        help="Benchmark against the default WSL distro instead of a container")
    args = parser.parse_args()

    plat = PLATFORM_CONFIG.get(platform.system(), {}).get("name", "unknown")
    today = date.today().isoformat()
    script_dir = Path(__file__).resolve().parent

    if not shutil.which("iperf3"):
        sys.exit("iperf3 is not installed on the host. Please install it first.")

    if args.wsl:
        run_wsl_benchmark(plat, today, script_dir)
    else:
        run_docker_benchmark(plat, today, script_dir)


if __name__ == "__main__":
    main()
