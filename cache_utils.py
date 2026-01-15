#!/usr/bin/env python3
"""
Cache setup utilities for benchmark tests.

This module contains functions to set up offline caches for npm and pip.
It only depends on cache_config.py, allowing Docker to cache this layer
independently of benchmark test parameters.
"""

import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from cache_config import (
    PIP_PACKAGES,
    PIP_EXTRA_INDEX_URL,
    NPM_PACKAGE_JSON,
    CACHE_DIR_NAME,
)


def _run_command(cmd: List[str], cwd: Optional[Path] = None, 
                 env: Optional[Dict] = None) -> Tuple[bool, str, float]:
    """Run a shell command and return success status, output, and duration"""
    import time
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=600  # 10 minute timeout
        )
        elapsed = time.time() - start_time
        output = result.stdout + result.stderr
        return result.returncode == 0, output, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return False, "Command timed out", elapsed
    except Exception as e:
        return False, str(e), time.time() - start_time


def _count_files_recursive(directory: Path) -> int:
    """Count all files recursively in a directory"""
    count = 0
    try:
        for root, dirs, files in os.walk(directory):
            count += len(files)
    except Exception:
        pass
    return count


def _get_directory_size(directory: Path) -> int:
    """Get total size of all files in a directory recursively"""
    total_size = 0
    try:
        for root, dirs, files in os.walk(directory):
            for f in files:
                total_size += os.path.getsize(os.path.join(root, f))
    except Exception:
        pass
    return total_size


def _format_size(size_bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def setup_npm_cache(cache_dir: Optional[Path] = None) -> bool:
    """
    Setup npm offline cache. Run this once with internet connection.
    
    Args:
        cache_dir: Directory to store caches. Defaults to ./benchmark_cache/
    
    Returns:
        True if cache was created successfully, False otherwise.
    """
    print("\n" + "=" * 70)
    print("SETTING UP NPM OFFLINE CACHE")
    print("=" * 70)
    
    if cache_dir is None:
        cache_dir = Path(".") / CACHE_DIR_NAME
    
    # Check if npm is available
    success, output, _ = _run_command(['npm', '--version'])
    if not success:
        print("npm is not installed. Skipping npm cache setup.")
        return False
    
    npm_cache_dir = cache_dir / "npm_cache"
    npm_test_dir = cache_dir / "npm_test_project"
    
    # Create cache directory
    cache_dir.mkdir(exist_ok=True)
    
    # Clean up old test directory if it exists
    if npm_test_dir.exists():
        shutil.rmtree(npm_test_dir)
    
    npm_test_dir.mkdir(parents=True)
    
    # Write package.json from config
    with open(npm_test_dir / "package.json", 'w') as f:
        json.dump(NPM_PACKAGE_JSON, f, indent=2)
    
    print("\nInstalling packages to create cache...")
    print(f"Cache directory: {npm_cache_dir.absolute()}")
    
    # Set up custom cache directory and install
    env = os.environ.copy()
    env['npm_config_cache'] = str(npm_cache_dir.absolute())
    
    success, output, duration = _run_command(
        ['npm', 'install'],
        cwd=npm_test_dir,
        env=env
    )
    
    if success:
        print(f"✓ npm cache created successfully in {duration:.2f} seconds")
        
        # Verify package-lock.json was created
        if (npm_test_dir / "package-lock.json").exists():
            print("✓ package-lock.json created")
        
        # Count cached files
        if npm_cache_dir.exists():
            cached_files = _count_files_recursive(npm_cache_dir)
            cache_size = _get_directory_size(npm_cache_dir)
            print(f"✓ Cache contains {cached_files} files ({_format_size(cache_size)})")
        
        # Clean up node_modules but keep package.json and package-lock.json
        if (npm_test_dir / "node_modules").exists():
            shutil.rmtree(npm_test_dir / "node_modules")
        
        return True
    else:
        print(f"✗ Failed to create npm cache: {output}")
        return False


def setup_pip_cache(cache_dir: Optional[Path] = None) -> bool:
    """
    Setup pip offline cache. Run this once with internet connection.
    
    Args:
        cache_dir: Directory to store caches. Defaults to ./benchmark_cache/
    
    Returns:
        True if cache was created successfully, False otherwise.
    """
    print("\n" + "=" * 70)
    print("SETTING UP PIP OFFLINE CACHE")
    print("=" * 70)
    
    if cache_dir is None:
        cache_dir = Path(".") / CACHE_DIR_NAME
    
    # Check if pip is available
    success, output, _ = _run_command(['pip', '--version'])
    if not success:
        print("pip is not installed. Skipping pip cache setup.")
        return False
    
    pip_cache_dir = cache_dir / "pip_wheels"
    
    # Create cache directory
    pip_cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Download popular packages (compatible with Python 3.12+)
    packages = PIP_PACKAGES
    
    print(f"\nDownloading packages to: {pip_cache_dir.absolute()}")
    print(f"Packages: {', '.join(packages)}")
    
    cmd = ['pip', 'download', '-d', str(pip_cache_dir),
           '--extra-index-url', PIP_EXTRA_INDEX_URL] + packages
    success, output, duration = _run_command(cmd)
    
    if success:
        print(f"✓ pip cache created successfully in {duration:.2f} seconds")
        
        # Count cached files
        wheel_files = list(pip_cache_dir.glob('*.whl')) + list(pip_cache_dir.glob('*.tar.gz'))
        cache_size = sum(f.stat().st_size for f in wheel_files)
        print(f"✓ Cache contains {len(wheel_files)} package files ({_format_size(cache_size)})")
        
        return True
    else:
        print(f"✗ Failed to create pip cache: {output}")
        return False


def setup_all_caches(cache_dir: Optional[Path] = None) -> Tuple[bool, bool]:
    """
    Setup all caches (npm and pip).
    
    Args:
        cache_dir: Directory to store caches. Defaults to ./benchmark_cache/
    
    Returns:
        Tuple of (npm_success, pip_success)
    """
    npm_success = setup_npm_cache(cache_dir)
    pip_success = setup_pip_cache(cache_dir)
    return npm_success, pip_success


if __name__ == "__main__":
    # Allow running this module directly for testing
    setup_all_caches()
