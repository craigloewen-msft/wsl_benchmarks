#!/usr/bin/env python3
"""
Setup script for creating offline caches for real-world benchmarks.
Run this once with an internet connection before running benchmarks offline.

This script only depends on cache_config.py and cache_utils.py, allowing
Docker to cache this layer independently of benchmark test parameters.
"""

from cache_utils import setup_npm_cache, setup_pip_cache, setup_git_cache


def main():
    print("=" * 70)
    print("BENCHMARK CACHE SETUP")
    print("=" * 70)
    print("\nThis script will download packages to create offline caches.")
    print("You only need to run this once with an internet connection.")
    print("The caches will be stored in ./benchmark_cache/")
    print("\n" + "=" * 70)
    
    # Setup npm cache
    npm_success = setup_npm_cache()
    
    # Setup pip cache
    pip_success = setup_pip_cache()
    
    # Setup git cache
    git_success = setup_git_cache()
    
    # Summary
    print("\n" + "=" * 70)
    print("SETUP SUMMARY")
    print("=" * 70)
    print(f"npm cache: {'✓ Ready' if npm_success else '✗ Failed or npm not available'}")
    print(f"pip cache: {'✓ Ready' if pip_success else '✗ Failed or pip not available'}")
    print(f"git cache: {'✓ Ready' if git_success else '✗ Failed or git not available'}")
    
    if npm_success or pip_success or git_success:
        print("\n✓ Setup complete! You can now run benchmarks offline.")
        print("  The benchmark_cache/ directory contains all necessary files.")
    else:
        print("\n⚠ No caches were created. Install npm, pip, and/or git to enable real-world tests.")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
