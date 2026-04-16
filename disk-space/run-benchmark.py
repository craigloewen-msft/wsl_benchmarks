#!/usr/bin/env python3
"""
Disk space benchmark for container technology.

Measures host disk space impact of building, running, and cleaning up
a container that compiles the Linux kernel.

Uses the appropriate container binary per platform:
  - Windows: wslc
  - Mac:     container
  - Linux:   docker
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

IMAGE_TAG = "disk-space-bench:latest"
CONTAINER_NAME = "disk-space-bench-run"
KERNEL_VERSION = "6.1.90"
KERNEL_URL = f"https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-{KERNEL_VERSION}.tar.xz"

PLATFORM_CONFIG = {
    "Windows": {"bin": "wslc", "name": "windows"},
    "Darwin": {"bin": "container", "name": "mac"},
    "Linux": {"bin": "docker", "name": "linux"},
}


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


# TODO: Platform-specific disk space measurement.
# The current placeholder uses basic OS-level disk usage queries.
# This may NOT accurately reflect container storage changes because:
#   - Mac: container data lives inside a VM disk image (e.g. Docker.raw).
#     Consider measuring that file's size directly.
#   - Linux: Docker stores data in /var/lib/docker by default.
#     Consider using `du -sb /var/lib/docker` or `docker system df`.
# In all cases, virtual disks may grow but not shrink automatically.
# This function should return disk space used in bytes.
def get_disk_space_used():
    system = platform.system()
    if system == "Windows":
        username = os.getlogin()
        vhdx = Path(f"C:/Users/{username}/AppData/Local/wslc/sessions"
                     f"/wslc-cli-{username}/storage.vhdx")
        if not vhdx.exists():
            sys.exit(f"VHDX not found: {vhdx}")
        return vhdx.stat().st_size
    else:
        result = run_capture(["df", "-k", "/"])
        line = result.strip().splitlines()[-1]
        used_kb = int(line.split()[2])
        return used_kb * 1024


def bytes_to_mb(b):
    return round(b / (1024 * 1024), 2)


def run(cmd, check=True, quiet=False):
    """Run a command, streaming output to the console."""
    if not quiet:
        print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=check,
                            capture_output=quiet)
    return result.returncode


def run_capture(cmd):
    """Run a command and return its stdout."""
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def container_exec(bin_name, cmd_str):
    """Run a bash command inside the running container."""
    run([bin_name, "exec", CONTAINER_NAME, "bash", "-c", cmd_str])


def main():
    bin_name = get_container_bin()
    plat = get_platform_name()
    today = date.today().isoformat()
    script_dir = Path(__file__).resolve().parent
    output_file = script_dir / f"{plat}-disk-space-{today}.json"

    print(f"Platform: {plat} | Binary: {bin_name}")
    print(f"Kernel:   Linux {KERNEL_VERSION}")
    print()

    try:
        # Step 1: Build the container image
        print("=== Step 1: Building container image ===")
        run([bin_name, "build", "-t", IMAGE_TAG, str(script_dir)])

        disk_after_build = get_disk_space_used()
        print(f"Disk used after image build: {bytes_to_mb(disk_after_build)} MB\n")

        # Step 2: Start container and compile the Linux kernel
        print("=== Step 2: Compiling Linux kernel ===")
        run([bin_name, "run", "-d", "--name", CONTAINER_NAME, IMAGE_TAG,
             "tail", "-f", "/dev/null"])

        build_cmd = (
            f"cd /build"
            f" && wget -q {KERNEL_URL}"
            f" && tar xf linux-{KERNEL_VERSION}.tar.xz"
            f" && cd linux-{KERNEL_VERSION}"
            f" && make defconfig"
            f" && make -j$(nproc)"
        )
        container_exec(bin_name, build_cmd)

        disk_after_compile = get_disk_space_used()
        print(f"Disk used after kernel compile: {bytes_to_mb(disk_after_compile)} MB\n")

        # Step 3: Delete kernel build files inside the container
        print("=== Step 3: Cleaning kernel build files ===")
        container_exec(bin_name, "rm -rf /build/*")

        disk_after_cleanup = get_disk_space_used()
        print(f"Disk used after kernel cleanup: {bytes_to_mb(disk_after_cleanup)} MB\n")

        # Step 4: Delete the container and image
        print("=== Step 4: Deleting container and image ===")
        run([bin_name, "rm", "-f", CONTAINER_NAME])
        run([bin_name, "rmi", IMAGE_TAG], check=False)

        disk_after_delete = get_disk_space_used()
        print(f"Disk used after container/image delete: {bytes_to_mb(disk_after_delete)} MB\n")

        # Write results
        results = {
            "platform": plat,
            "date": today,
            "container_tool": bin_name,
            "kernel_version": KERNEL_VERSION,
            "disk_space_mb": {
                "after_image_build": bytes_to_mb(disk_after_build),
                "after_kernel_compile": bytes_to_mb(disk_after_compile),
                "after_kernel_cleanup": bytes_to_mb(disk_after_cleanup),
                "after_container_delete": bytes_to_mb(disk_after_delete),
            },
        }

        output_file.write_text(json.dumps(results, indent=2) + "\n")
        print_success(output_file, results)

    finally:
        # Always try to clean up the container on failure
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
