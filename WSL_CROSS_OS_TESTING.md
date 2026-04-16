# Cross-OS File Performance Testing for WSL

This guide explains how to run file I/O benchmarks comparing WSL's native ext4 filesystem against the Windows NTFS filesystem (accessed via WSL's 9P mount).

## How it works

The benchmark's `--working-folder` argument controls **which filesystem is actually tested**. Pointing it at a native Linux path tests ext4; pointing it at `/mnt/c/...` tests NTFS over the 9P protocol. Run both, then compare the resulting JSON files.

The cache (npm packages, pip wheels, git repos) always lives next to the script on ext4. Only the benchmark I/O goes to the target filesystem.

---

## Prerequisites

- WSL with Python 3.12+
- `npm`, `pip`, and `git` installed in WSL (only needed for the package manager tests)

No Docker required.

---

## Step 1: One-time setup (needs internet)

Run this once from inside WSL, in the directory where you cloned the repo:

```bash
python3 setup_caches.py
```

This downloads npm packages, pip wheels, and a git repository into `benchmark_cache/` next to the script. All subsequent runs work offline.

---

## Step 2: Run benchmarks on WSL ext4 (native Linux filesystem)

```bash
python3 file_io_benchmark.py wsl-ext4
```

Results are saved to `benchmark_results_wsl-ext4.json`.

---

## Step 3: Run benchmarks on Windows NTFS (via WSL mount)

```bash
python3 file_io_benchmark.py wsl-ntfs --working-folder /mnt/c/Users/<your-username>/some-test-dir
```

Replace `/mnt/c/Users/<your-username>/some-test-dir` with any path on your Windows drive. The directory will be created if it doesn't exist.

Results are saved to that folder as `benchmark_results_wsl-ntfs.json`.

---

## Step 4: Compare results

Pass both JSON files to the plot generator:

```bash
python3 generate_plots.py benchmark_results_wsl-ext4.json /mnt/c/Users/<your-username>/some-test-dir/benchmark_results_wsl-ntfs.json
```

---

## Key flags

| Flag | Purpose |
|---|---|
| `wsl-ext4` / `wsl-ntfs` | Label used in the output filename and plots |
| `--working-folder` | **Where I/O happens** — change this to test different filesystems |
| `--runs 3` | Reduce iterations for a faster run |
| `--tests seq_write seq_read` | Run only specific tests |

### Available tests

| Name | What it measures |
|---|---|
| `seq_write` | Sequential write throughput (10 KB – 500 MB files) |
| `seq_read` | Sequential read throughput |
| `rand_write` | Random write IOPS and latency (4 KB blocks) |
| `rand_read` | Random read IOPS and latency |
| `metadata` | File creation and deletion speed |
| `npm` | Offline `npm ci` install |
| `pip` | Offline `pip install` into a venv |
| `git` | Offline `git clone` from a local bare repo |

### Quick run (fewer iterations)

For a faster sanity check, reduce the iteration count:

```bash
python3 file_io_benchmark.py wsl-ext4 --runs 1
python3 file_io_benchmark.py wsl-ntfs --working-folder /mnt/c/Users/<your-username>/some-test-dir --runs 1
```

### Skip package manager tests

If you only want raw I/O numbers (no npm/pip/git), skip setup entirely and run:

```bash
python3 file_io_benchmark.py wsl-ext4 --tests seq_write seq_read rand_write rand_read metadata
python3 file_io_benchmark.py wsl-ntfs --working-folder /mnt/c/Users/<your-username>/some-test-dir --tests seq_write seq_read rand_write rand_read metadata
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `setup_caches.py` fails with network errors | You need internet for the first run only. Check proxy/VPN settings. |
| npm/pip/git test says "cache not found" | Run `python3 setup_caches.py` first. The cache lives next to the script, not in the working folder. |
| Permission errors on `/mnt/c/...` | Make sure the target directory is writable. Try a path under your Windows user profile. |
| Very slow NTFS results | Expected — this is what the benchmark measures. 9P overhead on `/mnt/c` is significant for metadata-heavy workloads. |
