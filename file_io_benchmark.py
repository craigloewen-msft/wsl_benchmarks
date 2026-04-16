#!/usr/bin/env python3
"""
File I/O Performance Testing Script

Tests various file I/O operations with different file sizes and patterns
to measure storage performance characteristics.
"""

import os
import time
import shutil
import random
import statistics
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json

from cache_config import (
    PIP_PACKAGES,
    PIP_EXTRA_INDEX_URL,
    NPM_PACKAGE_JSON,
    CACHE_DIR_NAME,
    GIT_REPOS,
)


class FileIOBenchmark:

    def __init__(self, test_dir: str = "benchmark_temp", data_size_gb: float = 2.0, name: str = "default", working_dir: str = "./"):
        self.working_dir = Path(working_dir).resolve()
        self.script_dir = Path(__file__).parent.resolve()  # Directory where the script lives
        self.test_dir = self.working_dir / test_dir
        self.data_size_gb = data_size_gb
        self.name = name
        self.results = {}
        self.all_runs = []  # Store results from all runs
        self.cache_dir = self.script_dir / "benchmark_cache"  # Directory for offline caches (always next to the script)
        
        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy benchmark_cache from script directory if it doesn't exist in working directory
        self._ensure_cache_exists()
    
    def _drop_caches(self) -> bool:
        """Drop filesystem caches to ensure consistent benchmark results.
        
        On Linux, this syncs the filesystem and drops page cache, dentries, and inodes.
        Requires root privileges or sudo access.
        
        Returns:
            True if cache was successfully dropped, False otherwise.
        """
        print("  Dropping filesystem caches...")
            # First sync to flush any pending writes
        subprocess.run(['sync'], check=True)
        
        # Try to drop caches (requires root)
        # echo 3 drops page cache, dentries, and inodes
        result = subprocess.run(
            [ 'sh', '-c', 'echo 3 > /proc/sys/vm/drop_caches'],
            capture_output=True,
            text=True
        )
            
        if result.returncode == 0:
            print("  Filesystem caches dropped successfully.")
            return True
        else:
            return False

    def _ensure_cache_exists(self):
        """Copy benchmark_cache from script directory to working directory if needed"""
        source_cache = self.script_dir / "benchmark_cache"

        if not self.cache_dir.exists():
            if source_cache.exists():
                print(f"Copying benchmark_cache from {source_cache} to {self.cache_dir}...")
                shutil.copytree(source_cache, self.cache_dir)
                print(f"✓ benchmark_cache copied successfully")

                # Set permissive permissions and ownership
                print(f"Setting permissions on {self.cache_dir}...")
                try:
                    # Make all files and directories readable, writable, and executable by everyone
                    subprocess.run(['chmod', '-R', '777', str(self.cache_dir)], check=False)

                    # Try to change ownership to current user (may not be needed/possible in all environments)
                    import pwd
                    try:
                        uid = os.getuid()
                        gid = os.getgid()
                        subprocess.run(['chown', '-R', f'{uid}:{gid}', str(self.cache_dir)], check=False)
                    except:
                        pass  # Ignore errors if chown fails (e.g., already correct owner)

                    print(f"✓ Permissions set successfully")
                except Exception as e:
                    print(f"Warning: Could not set all permissions: {e}")
            else:
                print(f"Warning: benchmark_cache not found at {source_cache}")
                print("Some tests may be skipped. Run setup_caches.py first to create the cache.")
        else:
            print(f"Using existing benchmark_cache at {self.cache_dir}")
        
    def setup(self):
        """Create test directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir(parents=True)
        
    def cleanup(self):
        """Remove test directory"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _generate_data(self, size_bytes: int) -> bytes:
        """Generate random data of specified size"""
        return os.urandom(size_bytes)
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    
    def _format_speed(self, bytes_per_sec: float) -> str:
        """Format speed to human readable format"""
        return self._format_size(bytes_per_sec) + "/s"
    
    def test_sequential_write(self, file_size: int, block_size: int = 64*1024) -> Dict:
        """Test sequential write performance"""
        filepath = self.test_dir / "sequential_write_test.bin"
        data_block = self._generate_data(block_size)
        blocks_to_write = file_size // block_size
        
        start_time = time.time()
        with open(filepath, 'wb') as f:
            for _ in range(blocks_to_write):
                f.write(data_block)
            f.flush()
            os.fsync(f.fileno())  # Ensure data is written to disk
        
        elapsed = time.time() - start_time
        speed = file_size / elapsed if elapsed > 0 else 0
        
        filepath.unlink()
        
        return {
            'duration_sec': elapsed,
            'speed_bytes_per_sec': speed,
            'speed_formatted': self._format_speed(speed)
        }
    
    def test_sequential_read(self, file_size: int, block_size: int = 64*1024) -> Dict:
        """Test sequential read performance"""
        filepath = self.test_dir / "sequential_read_test.bin"
        
        # First create the file
        data_block = self._generate_data(block_size)
        blocks_to_write = file_size // block_size
        with open(filepath, 'wb') as f:
            for _ in range(blocks_to_write):
                f.write(data_block)
        
        # Clear file cache by reopening
        # Note: True cache clearing requires OS-specific commands
        
        start_time = time.time()
        with open(filepath, 'rb') as f:
            while f.read(block_size):
                pass
        
        elapsed = time.time() - start_time
        speed = file_size / elapsed if elapsed > 0 else 0
        
        filepath.unlink()
        
        return {
            'duration_sec': elapsed,
            'speed_bytes_per_sec': speed,
            'speed_formatted': self._format_speed(speed)
        }
    
    def test_random_write(self, file_size: int, num_operations: int = 1000, 
                         block_size: int = 4096) -> Dict:
        """Test random write performance (IOPS)"""
        filepath = self.test_dir / "random_write_test.bin"
        
        # Pre-allocate file
        with open(filepath, 'wb') as f:
            f.seek(file_size - 1)
            f.write(b'\0')
        
        data_block = self._generate_data(block_size)
        max_offset = file_size - block_size
        
        start_time = time.time()
        with open(filepath, 'r+b') as f:
            for _ in range(num_operations):
                offset = random.randint(0, max_offset // block_size) * block_size
                f.seek(offset)
                f.write(data_block)
            f.flush()
            os.fsync(f.fileno())
        
        elapsed = time.time() - start_time
        iops = num_operations / elapsed if elapsed > 0 else 0
        latency_ms = (elapsed / num_operations * 1000) if num_operations > 0 else 0
        
        filepath.unlink()
        
        return {
            'duration_sec': elapsed,
            'iops': iops,
            'avg_latency_ms': latency_ms,
            'operations': num_operations
        }
    
    def test_random_read(self, file_size: int, num_operations: int = 1000,
                        block_size: int = 4096) -> Dict:
        """Test random read performance (IOPS)"""
        filepath = self.test_dir / "random_read_test.bin"
        
        # Create file with random data
        with open(filepath, 'wb') as f:
            data = self._generate_data(file_size)
            f.write(data)
        
        max_offset = file_size - block_size
        
        start_time = time.time()
        with open(filepath, 'rb') as f:
            for _ in range(num_operations):
                offset = random.randint(0, max_offset // block_size) * block_size
                f.seek(offset)
                f.read(block_size)
        
        elapsed = time.time() - start_time
        iops = num_operations / elapsed if elapsed > 0 else 0
        latency_ms = (elapsed / num_operations * 1000) if num_operations > 0 else 0
        
        filepath.unlink()
        
        return {
            'duration_sec': elapsed,
            'iops': iops,
            'avg_latency_ms': latency_ms,
            'operations': num_operations
        }
    
    def test_file_creation(self, num_files: int = 1000, file_size: int = 4096) -> Dict:
        """Test small file creation performance (metadata operations)"""
        data = self._generate_data(file_size)
        
        start_time = time.time()
        for i in range(num_files):
            filepath = self.test_dir / f"small_file_{i}.bin"
            with open(filepath, 'wb') as f:
                f.write(data)
        
        elapsed = time.time() - start_time
        files_per_sec = num_files / elapsed if elapsed > 0 else 0
        
        return {
            'duration_sec': elapsed,
            'files_created': num_files,
            'files_per_sec': files_per_sec,
            'avg_time_per_file_ms': (elapsed / num_files * 1000) if num_files > 0 else 0
        }
    
    def test_file_deletion(self, num_files: int = 1000) -> Dict:
        """Test file deletion performance"""
        # Files should already exist from creation test
        files = list(self.test_dir.glob("small_file_*.bin"))
        actual_count = len(files)
        
        start_time = time.time()
        for filepath in files:
            filepath.unlink()
        
        elapsed = time.time() - start_time
        files_per_sec = actual_count / elapsed if elapsed > 0 else 0
        
        return {
            'duration_sec': elapsed,
            'files_deleted': actual_count,
            'files_per_sec': files_per_sec,
            'avg_time_per_file_ms': (elapsed / actual_count * 1000) if actual_count > 0 else 0
        }
    
    def _run_command(self, cmd: List[str], cwd: Optional[Path] = None,
                     env: Optional[Dict] = None, timeout: int = 300,
                     check: bool = True) -> Tuple[bool, str, float]:
        """Run a shell command and return success status, output, and duration

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory for command
            env: Environment variables
            timeout: Timeout in seconds (default: 300)
            check: If True, raise exception on non-zero return code (default: True)

        Raises:
            subprocess.TimeoutExpired: If command times out
            subprocess.CalledProcessError: If command fails and check=True
            Exception: For other errors
        """
        start_time = time.time()
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check
        )
        elapsed = time.time() - start_time
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return success, output, elapsed
    
    def _count_files_recursive(self, directory: Path) -> int:
        """Count all files recursively in a directory"""
        count = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    count += 1
        except Exception:
            pass
        return count
    
    def _get_directory_size(self, directory: Path) -> int:
        """Get total size of all files in a directory recursively"""
        total_size = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception:
            pass
        return total_size
    
    def test_npm_install_offline(self) -> Optional[Dict]:
        """Test npm install using offline cache"""
        npm_cache_dir = self.cache_dir / "npm_cache"
        npm_test_project = self.cache_dir / "npm_test_project"
        
        # Check if cache exists
        if not npm_cache_dir.exists() or not npm_test_project.exists():
            print("  npm cache not found. Run setup_npm_cache() first.")
            return None
        
        # Check if npm is available
        success, _, _ = self._run_command(['npm', '--version'], check=False)
        if not success:
            print("  npm is not installed. Skipping test.")
            return None
        
        # Create test directory
        test_install_dir = self.test_dir / "npm_install_test"
        if test_install_dir.exists():
            shutil.rmtree(test_install_dir)
        test_install_dir.mkdir(parents=True)
        
        # Copy package.json and package-lock.json
        shutil.copy(npm_test_project / "package.json", test_install_dir)
        shutil.copy(npm_test_project / "package-lock.json", test_install_dir)
        
        # Run npm ci with offline cache
        env = os.environ.copy()
        env['npm_config_cache'] = str(npm_cache_dir.absolute())

        start_time = time.time()
        try:
            success, output, duration = self._run_command(
                ['npm', 'ci', '--offline', '--prefer-offline'],
                cwd=test_install_dir,
                env=env
            )
        except subprocess.CalledProcessError as e:
            error_output = e.stdout + e.stderr if e.stdout and e.stderr else (e.stdout or e.stderr or "")
            raise RuntimeError(
                f"npm ci failed with exit code {e.returncode}\n"
                f"Command: {' '.join(e.cmd)}\n"
                f"Working directory: {test_install_dir}\n"
                f"Output:\n{error_output}"
            ) from e

        elapsed = time.time() - start_time

        # Count installed files
        node_modules = test_install_dir / "node_modules"
        if node_modules.exists():
            files_created = self._count_files_recursive(node_modules)
            total_size = self._get_directory_size(node_modules)
        else:
            files_created = 0
            total_size = 0

        # Clean up
        shutil.rmtree(test_install_dir)

        return {
            'duration_sec': elapsed,
            'files_created': files_created,
            'total_bytes': total_size,
            'total_size_formatted': self._format_size(total_size),
            'files_per_sec': files_created / elapsed if elapsed > 0 else 0,
            'speed_bytes_per_sec': total_size / elapsed if elapsed > 0 else 0,
            'speed_formatted': self._format_speed(total_size / elapsed) if elapsed > 0 else 'N/A'
        }
    
    def test_pip_install_offline(self) -> Optional[Dict]:
        """Test pip install using offline wheel cache"""
        pip_cache_dir = self.cache_dir / "pip_wheels"
        
        # Check if cache exists
        if not pip_cache_dir.exists():
            print("  pip cache not found. Run setup_pip_cache() first.")
            return None
        
        # Check if pip is available
        success, _, _ = self._run_command(['pip', '--version'], check=False)
        if not success:
            print("  pip is not installed. Skipping test.")
            return None
        
        # Create a virtual environment for testing
        venv_dir = self.test_dir / "pip_test_venv"
        if venv_dir.exists():
            shutil.rmtree(venv_dir)
        
        # Create virtual environment
        success, output, _ = self._run_command(['python3', '-m', 'venv', str(venv_dir)])

        # Determine pip executable path
        if os.name == 'nt':  # Windows
            pip_exe = venv_dir / "Scripts" / "pip.exe"
        else:  # Unix-like
            pip_exe = venv_dir / "bin" / "pip"

        # Get list of packages to install
        packages = PIP_PACKAGES

        # Install from local cache
        cmd = [
            str(pip_exe), 'install',
            '--no-index',
            '--find-links=' + str(pip_cache_dir.absolute())
        ] + packages

        start_time = time.time()
        # Use longer timeout for pip install (30 minutes for slow file systems)

        try:
            success, output, duration = self._run_command(
                cmd, timeout=1800
            )
        except subprocess.CalledProcessError as e:
            error_output = e.stdout + e.stderr if e.stdout and e.stderr else (e.stdout or e.stderr or "")
            raise RuntimeError(
                f"pip install failed with exit code {e.returncode}\n"
                f"Command: {' '.join(e.cmd)}\n"
                f"Output:\n{error_output}"
            ) from e
        
        elapsed = time.time() - start_time

        # Count installed files
        site_packages = venv_dir / "lib"
        if site_packages.exists():
            files_created = self._count_files_recursive(site_packages)
            total_size = self._get_directory_size(site_packages)
        else:
            files_created = 0
            total_size = 0

        # Clean up
        shutil.rmtree(venv_dir)

        return {
            'duration_sec': elapsed,
            'files_created': files_created,
            'total_bytes': total_size,
            'total_size_formatted': self._format_size(total_size),
            'files_per_sec': files_created / elapsed if elapsed > 0 else 0,
            'speed_bytes_per_sec': total_size / elapsed if elapsed > 0 else 0,
            'speed_formatted': self._format_speed(total_size / elapsed) if elapsed > 0 else 'N/A',
            'packages_installed': len(packages)
        }
    
    def test_git_clone_offline(self) -> Optional[Dict]:
        """Test git clone using offline bare repository cache"""
        git_cache_dir = self.cache_dir / "git_repos"
        
        # Check if cache exists
        if not git_cache_dir.exists():
            print("  git cache not found. Run setup_git_cache() first.")
            return None
        
        # Check if git is available
        success, _, _ = self._run_command(['git', '--version'], check=False)
        if not success:
            print("  git is not installed. Skipping test.")
            return None
        
        # Check if we have any cached repositories
        if not GIT_REPOS:
            print("  No git repositories configured.")
            return None
        
        total_duration = 0
        total_files = 0
        total_bytes = 0
        repos_cloned = 0
        
        for repo_config in GIT_REPOS:
            repo_name = repo_config['name']
            bare_repo_path = git_cache_dir / f"{repo_name}.git"

            if not bare_repo_path.exists():
                print(f"  Cache for {repo_name} not found. Skipping.")
                continue

            # Mark the bare repository as safe (to avoid "dubious ownership" errors)
            self._run_command(['git', 'config', '--global', '--add', 'safe.directory', str(bare_repo_path.absolute())], check=False)

            # Create destination directory for clone
            clone_dest = self.test_dir / f"git_clone_{repo_name}"
            if clone_dest.exists():
                shutil.rmtree(clone_dest)

            # Clone from local bare repository (offline)
            start_time = time.time()
            success, output, duration = self._run_command(
                ['git', 'clone', str(bare_repo_path.absolute()), str(clone_dest)]
            )
            elapsed = time.time() - start_time

            # Count cloned files
            files_created = self._count_files_recursive(clone_dest)
            clone_size = self._get_directory_size(clone_dest)

            total_duration += elapsed
            total_files += files_created
            total_bytes += clone_size
            repos_cloned += 1

            print(f"    {repo_name}: {files_created} files, {self._format_size(clone_size)} in {elapsed:.2f}s")

            # Clean up
            shutil.rmtree(clone_dest)

        return {
            'duration_sec': total_duration,
            'files_created': total_files,
            'total_bytes': total_bytes,
            'total_size_formatted': self._format_size(total_bytes),
            'files_per_sec': total_files / total_duration if total_duration > 0 else 0,
            'speed_bytes_per_sec': total_bytes / total_duration if total_duration > 0 else 0,
            'speed_formatted': self._format_speed(total_bytes / total_duration) if total_duration > 0 else 'N/A',
            'repos_cloned': repos_cloned
        }
    
    def run_benchmark_suite(self, selected_tests=None):
        """Run complete benchmark suite or selected tests

        Args:
            selected_tests: Optional list of test categories to run.
                           Options: 'seq_write', 'seq_read', 'rand_write', 'rand_read',
                                   'metadata', 'npm', 'pip', 'git'
                           If None, all tests will run.
        """
        print("=" * 70)
        print("FILE I/O PERFORMANCE BENCHMARK")
        print("=" * 70)
        print(f"Test Directory: {self.test_dir.absolute()}")
        if selected_tests:
            print(f"Selected Tests: {', '.join(selected_tests)}")
        print()

        self.results = {}  # Reset results for this run

        self.setup()

        # Define test configurations with individual data sizes
        # Format: (name, file_size, total_data_size_for_this_test)
        test_configs = [
            ('Very Tiny Files (10 KB each)', 10 * 1024, 25 * 1024 * 1024),
            ('Tiny Files (100 KB each)', 100 * 1024, 100 * 1024 * 1024),  # 100 MB total
            ('Small Files (1 MB each)', 1 * 1024 * 1024, 500 * 1024 * 1024),  # 500 MB total
            ('Medium Files (10 MB each)', 10 * 1024 * 1024, int(self.data_size_gb * 1024 * 1024 * 1024)),
            ('Large Files (100 MB each)', 100 * 1024 * 1024, int(self.data_size_gb * 1024 * 1024 * 1024)),
            ('Very Large Files (500 MB each)', 500 * 1024 * 1024, int(self.data_size_gb * 1024 * 1024 * 1024)),
        ]
        
        # Sequential Write Tests
        if selected_tests is None or 'seq_write' in selected_tests:
            print("\n" + "=" * 70)
            print(f"SEQUENTIAL WRITE TESTS")
            print("=" * 70)
            for name, size, total_data_size in test_configs:
                num_files = total_data_size // size
                print(f"\nTesting {name} ({num_files} file(s), {self._format_size(total_data_size)} total)...")
                total_time = 0
                total_bytes = 0
                for i in range(num_files):
                    result = self.test_sequential_write(size)
                    total_time += result['duration_sec']
                    total_bytes += size

                avg_speed = total_bytes / total_time if total_time > 0 else 0
                self.results[f'seq_write_{size}'] = {
                    'duration_sec': total_time,
                    'speed_bytes_per_sec': avg_speed,
                    'speed_formatted': self._format_speed(avg_speed),
                    'file_size': size,
                    'total_bytes': total_bytes
                }
                print(f"  Total Duration: {total_time:.3f} seconds")
                print(f"  Average Speed: {self._format_speed(avg_speed)}")
                print(f"  Files Written: {num_files}")
        
        # Sequential Read Tests
        if selected_tests is None or 'seq_read' in selected_tests:
            print("\n" + "=" * 70)
            print(f"SEQUENTIAL READ TESTS")
            print("=" * 70)
            for name, size, total_data_size in test_configs:
                num_files = total_data_size // size
                print(f"\nTesting {name} ({num_files} file(s), {self._format_size(total_data_size)} total)...")
                total_time = 0
                total_bytes = 0
                for i in range(num_files):
                    result = self.test_sequential_read(size)
                    total_time += result['duration_sec']
                    total_bytes += size

                avg_speed = total_bytes / total_time if total_time > 0 else 0
                self.results[f'seq_read_{size}'] = {
                    'duration_sec': total_time,
                    'speed_bytes_per_sec': avg_speed,
                    'speed_formatted': self._format_speed(avg_speed),
                    'file_size': size,
                    'total_bytes': total_bytes
                }
                print(f"  Total Duration: {total_time:.3f} seconds")
                print(f"  Average Speed: {self._format_speed(avg_speed)}")
                print(f"  Files Read: {num_files}")
        
        # Random Write Tests
        if selected_tests is None or 'rand_write' in selected_tests:
            print("\n" + "=" * 70)
            print("RANDOM WRITE TESTS (4KB blocks)")
            print("=" * 70)
            random_test_configs = [
                ('100 MB file', 100 * 1024 * 1024, 5000),
                ('500 MB file', 500 * 1024 * 1024, 10000),
            ]
            for name, size, ops in random_test_configs:
                print(f"\nTesting {name} ({ops} operations)...")
                result = self.test_random_write(size, ops)
                self.results[f'rand_write_{size}'] = result
                print(f"  Duration: {result['duration_sec']:.3f} seconds")
                print(f"  IOPS: {result['iops']:.2f}")
                print(f"  Avg Latency: {result['avg_latency_ms']:.3f} ms")
        
        # Random Read Tests
        if selected_tests is None or 'rand_read' in selected_tests:
            print("\n" + "=" * 70)
            print("RANDOM READ TESTS (4KB blocks)")
            print("=" * 70)
            random_test_configs = [
                ('100 MB file', 100 * 1024 * 1024, 5000),
                ('500 MB file', 500 * 1024 * 1024, 10000),
            ]
            for name, size, ops in random_test_configs:
                print(f"\nTesting {name} ({ops} operations)...")
                result = self.test_random_read(size, ops)
                self.results[f'rand_read_{size}'] = result
                print(f"  Duration: {result['duration_sec']:.3f} seconds")
                print(f"  IOPS: {result['iops']:.2f}")
                print(f"  Avg Latency: {result['avg_latency_ms']:.3f} ms")
        
        # Metadata Operations
        if selected_tests is None or 'metadata' in selected_tests:
            print("\n" + "=" * 70)
            print("METADATA OPERATIONS (Small File Tests)")
            print("=" * 70)

            print("\nTesting file creation (5000 files of 4KB each)...")
            result = self.test_file_creation(5000, 4096)
            self.results['file_creation'] = result
            print(f"  Duration: {result['duration_sec']:.3f} seconds")
            print(f"  Files per second: {result['files_per_sec']:.2f}")
            print(f"  Avg time per file: {result['avg_time_per_file_ms']:.3f} ms")

            print("\nTesting file deletion (5000 files)...")
            result = self.test_file_deletion(5000)
            self.results['file_deletion'] = result
            print(f"  Duration: {result['duration_sec']:.3f} seconds")
            print(f"  Files per second: {result['files_per_sec']:.2f}")
            print(f"  Avg time per file: {result['avg_time_per_file_ms']:.3f} ms")
        
        # Real-world package manager tests
        if selected_tests is None or any(t in selected_tests for t in ['npm', 'pip', 'git']):
            print("\n" + "=" * 70)
            print("REAL-WORLD TESTS (Package Managers & Git)")
            print("=" * 70)

        if selected_tests is None or 'npm' in selected_tests:
            print("\nTesting npm install (offline)...")
            result = self.test_npm_install_offline()
            if result:
                self.results['npm_install'] = result
                print(f"  Duration: {result['duration_sec']:.3f} seconds")
                print(f"  Files created: {result['files_created']}")
                print(f"  Total size: {result['total_size_formatted']}")
                print(f"  Average speed: {result['speed_formatted']}")
                print(f"  Files per second: {result['files_per_sec']:.2f}")
            else:
                print("  Skipped (cache not available or npm not installed)")

        if selected_tests is None or 'pip' in selected_tests:
            print("\nTesting pip install (offline)...")
            result = self.test_pip_install_offline()
            if result:
                self.results['pip_install'] = result
                print(f"  Duration: {result['duration_sec']:.3f} seconds")
                print(f"  Files created: {result['files_created']}")
                print(f"  Packages installed: {result['packages_installed']}")
                print(f"  Total size: {result['total_size_formatted']}")
                print(f"  Average speed: {result['speed_formatted']}")
                print(f"  Files per second: {result['files_per_sec']:.2f}")
            else:
                print("  Skipped (cache not available or pip not installed)")

        if selected_tests is None or 'git' in selected_tests:
            print("\nTesting git clone (offline)...")
            result = self.test_git_clone_offline()
            if result:
                self.results['git_clone'] = result
                print(f"  Duration: {result['duration_sec']:.3f} seconds")
                print(f"  Files created: {result['files_created']}")
                print(f"  Repositories cloned: {result['repos_cloned']}")
                print(f"  Total size: {result['total_size_formatted']}")
                print(f"  Average speed: {result['speed_formatted']}")
                print(f"  Files per second: {result['files_per_sec']:.2f}")
            else:
                print("  Skipped (cache not available or git not installed)")

        # Store results from this run
        self.cleanup()
        return self.results
    
    def _print_summary(self):
        """Print summary of results"""
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        # Extract key metrics
        seq_write_speeds = [v['speed_bytes_per_sec'] for k, v in self.results.items() 
                           if k.startswith('seq_write_')]
        seq_read_speeds = [v['speed_bytes_per_sec'] for k, v in self.results.items() 
                          if k.startswith('seq_read_')]
        rand_write_iops = [v['iops'] for k, v in self.results.items() 
                          if k.startswith('rand_write_')]
        rand_read_iops = [v['iops'] for k, v in self.results.items() 
                         if k.startswith('rand_read_')]
        
        if seq_write_speeds:
            avg_write = statistics.mean(seq_write_speeds)
            print(f"\nAverage Sequential Write Speed: {self._format_speed(avg_write)}")
        
        if seq_read_speeds:
            avg_read = statistics.mean(seq_read_speeds)
            print(f"Average Sequential Read Speed: {self._format_speed(avg_read)}")
        
        if rand_write_iops:
            avg_write_iops = statistics.mean(rand_write_iops)
            print(f"\nAverage Random Write IOPS (4KB): {avg_write_iops:.2f}")
        
        if rand_read_iops:
            avg_read_iops = statistics.mean(rand_read_iops)
            print(f"Average Random Read IOPS (4KB): {avg_read_iops:.2f}")
        
        if 'file_creation' in self.results:
            print(f"\nFile Creation Rate: {self.results['file_creation']['files_per_sec']:.2f} files/sec")
        
        if 'file_deletion' in self.results:
            print(f"File Deletion Rate: {self.results['file_deletion']['files_per_sec']:.2f} files/sec")
        
        if 'npm_install' in self.results:
            print(f"\nnpm install (offline): {self.results['npm_install']['duration_sec']:.3f} sec")
            print(f"  Files created: {self.results['npm_install']['files_created']}")
            print(f"  Speed: {self.results['npm_install']['speed_formatted']}")
        
        if 'pip_install' in self.results:
            print(f"\npip install (offline): {self.results['pip_install']['duration_sec']:.3f} sec")
            print(f"  Files created: {self.results['pip_install']['files_created']}")
            print(f"  Speed: {self.results['pip_install']['speed_formatted']}")
        
        if 'git_clone' in self.results:
            print(f"\ngit clone (offline): {self.results['git_clone']['duration_sec']:.3f} sec")
            print(f"  Files created: {self.results['git_clone']['files_created']}")
            print(f"  Repos cloned: {self.results['git_clone']['repos_cloned']}")
            print(f"  Speed: {self.results['git_clone']['speed_formatted']}")
    
    def _calculate_statistics(self, values: List[float]) -> Dict:
        """Calculate mean and standard deviation for a list of values"""
        if not values:
            return {'mean': 0, 'std_dev': 0}
        
        mean = statistics.mean(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0
        
        return {'mean': mean, 'std_dev': std_dev}
    
    def _print_aggregated_results(self):
        """Print aggregated statistics across all runs"""
        print("\n" + "=" * 70)
        print("AGGREGATED RESULTS ACROSS ALL RUNS")
        print("=" * 70)
        
        if not self.all_runs:
            print("No results to aggregate.")
            return
        
        num_runs = len(self.all_runs)
        print(f"\nNumber of runs: {num_runs}")
        
        # Collect all metrics from all runs
        metrics = {}
        
        # Go through each run and collect values for each metric
        for run_results in self.all_runs:
            for test_name, test_data in run_results.items():
                if test_name not in metrics:
                    metrics[test_name] = {}
                
                for metric_name, value in test_data.items():
                    if isinstance(value, (int, float)):
                        if metric_name not in metrics[test_name]:
                            metrics[test_name][metric_name] = []
                        metrics[test_name][metric_name].append(value)
        
        # Print sequential write results
        print("\n" + "-" * 70)
        print("SEQUENTIAL WRITE PERFORMANCE")
        print("-" * 70)
        for test_name in sorted([k for k in metrics.keys() if k.startswith('seq_write_')]):
            file_size = int(test_name.split('_')[-1])
            print(f"\n{self._format_size(file_size)} Files:")
            
            if 'speed_bytes_per_sec' in metrics[test_name]:
                stats = self._calculate_statistics(metrics[test_name]['speed_bytes_per_sec'])
                print(f"  Speed: {self._format_speed(stats['mean'])} ± {self._format_speed(stats['std_dev'])}")
                print(f"  (Mean ± Std Dev)")
        
        # Print sequential read results
        print("\n" + "-" * 70)
        print("SEQUENTIAL READ PERFORMANCE")
        print("-" * 70)
        for test_name in sorted([k for k in metrics.keys() if k.startswith('seq_read_')]):
            file_size = int(test_name.split('_')[-1])
            print(f"\n{self._format_size(file_size)} Files:")
            
            if 'speed_bytes_per_sec' in metrics[test_name]:
                stats = self._calculate_statistics(metrics[test_name]['speed_bytes_per_sec'])
                print(f"  Speed: {self._format_speed(stats['mean'])} ± {self._format_speed(stats['std_dev'])}")
                print(f"  (Mean ± Std Dev)")
        
        # Print random write results
        print("\n" + "-" * 70)
        print("RANDOM WRITE PERFORMANCE (4KB blocks)")
        print("-" * 70)
        for test_name in sorted([k for k in metrics.keys() if k.startswith('rand_write_')]):
            file_size = int(test_name.split('_')[-1])
            print(f"\n{self._format_size(file_size)} Files:")
            
            if 'iops' in metrics[test_name]:
                stats = self._calculate_statistics(metrics[test_name]['iops'])
                print(f"  IOPS: {stats['mean']:.2f} ± {stats['std_dev']:.2f}")
            
            if 'avg_latency_ms' in metrics[test_name]:
                stats = self._calculate_statistics(metrics[test_name]['avg_latency_ms'])
                print(f"  Latency: {stats['mean']:.3f} ms ± {stats['std_dev']:.3f} ms")
        
        # Print random read results
        print("\n" + "-" * 70)
        print("RANDOM READ PERFORMANCE (4KB blocks)")
        print("-" * 70)
        for test_name in sorted([k for k in metrics.keys() if k.startswith('rand_read_')]):
            file_size = int(test_name.split('_')[-1])
            print(f"\n{self._format_size(file_size)} Files:")
            
            if 'iops' in metrics[test_name]:
                stats = self._calculate_statistics(metrics[test_name]['iops'])
                print(f"  IOPS: {stats['mean']:.2f} ± {stats['std_dev']:.2f}")
            
            if 'avg_latency_ms' in metrics[test_name]:
                stats = self._calculate_statistics(metrics[test_name]['avg_latency_ms'])
                print(f"  Latency: {stats['mean']:.3f} ms ± {stats['std_dev']:.3f} ms")
        
        # Print metadata operation results
        print("\n" + "-" * 70)
        print("METADATA OPERATIONS")
        print("-" * 70)
        
        if 'file_creation' in metrics:
            print(f"\nFile Creation:")
            if 'files_per_sec' in metrics['file_creation']:
                stats = self._calculate_statistics(metrics['file_creation']['files_per_sec'])
                print(f"  Rate: {stats['mean']:.2f} ± {stats['std_dev']:.2f} files/sec")
            if 'avg_time_per_file_ms' in metrics['file_creation']:
                stats = self._calculate_statistics(metrics['file_creation']['avg_time_per_file_ms'])
                print(f"  Avg Time: {stats['mean']:.3f} ms ± {stats['std_dev']:.3f} ms")
        
        if 'file_deletion' in metrics:
            print(f"\nFile Deletion:")
            if 'files_per_sec' in metrics['file_deletion']:
                stats = self._calculate_statistics(metrics['file_deletion']['files_per_sec'])
                print(f"  Rate: {stats['mean']:.2f} ± {stats['std_dev']:.2f} files/sec")
            if 'avg_time_per_file_ms' in metrics['file_deletion']:
                stats = self._calculate_statistics(metrics['file_deletion']['avg_time_per_file_ms'])
                print(f"  Avg Time: {stats['mean']:.3f} ms ± {stats['std_dev']:.3f} ms")
        
        # Print real-world test results
        print("\n" + "-" * 70)
        print("REAL-WORLD TESTS (Package Managers & Git)")
        print("-" * 70)
        
        if 'npm_install' in metrics:
            print(f"\nnpm install (offline):")
            if 'duration_sec' in metrics['npm_install']:
                stats = self._calculate_statistics(metrics['npm_install']['duration_sec'])
                print(f"  Duration: {stats['mean']:.3f} sec ± {stats['std_dev']:.3f} sec")
            if 'files_created' in metrics['npm_install']:
                stats = self._calculate_statistics(metrics['npm_install']['files_created'])
                print(f"  Files Created: {stats['mean']:.0f} ± {stats['std_dev']:.0f}")
            if 'speed_bytes_per_sec' in metrics['npm_install']:
                stats = self._calculate_statistics(metrics['npm_install']['speed_bytes_per_sec'])
                print(f"  Speed: {self._format_speed(stats['mean'])} ± {self._format_speed(stats['std_dev'])}")
        
        if 'pip_install' in metrics:
            print(f"\npip install (offline):")
            if 'duration_sec' in metrics['pip_install']:
                stats = self._calculate_statistics(metrics['pip_install']['duration_sec'])
                print(f"  Duration: {stats['mean']:.3f} sec ± {stats['std_dev']:.3f} sec")
            if 'files_created' in metrics['pip_install']:
                stats = self._calculate_statistics(metrics['pip_install']['files_created'])
                print(f"  Files Created: {stats['mean']:.0f} ± {stats['std_dev']:.0f}")
            if 'speed_bytes_per_sec' in metrics['pip_install']:
                stats = self._calculate_statistics(metrics['pip_install']['speed_bytes_per_sec'])
                print(f"  Speed: {self._format_speed(stats['mean'])} ± {self._format_speed(stats['std_dev'])}")
        
        if 'git_clone' in metrics:
            print(f"\ngit clone (offline):")
            if 'duration_sec' in metrics['git_clone']:
                stats = self._calculate_statistics(metrics['git_clone']['duration_sec'])
                print(f"  Duration: {stats['mean']:.3f} sec ± {stats['std_dev']:.3f} sec")
            if 'files_created' in metrics['git_clone']:
                stats = self._calculate_statistics(metrics['git_clone']['files_created'])
                print(f"  Files Created: {stats['mean']:.0f} ± {stats['std_dev']:.0f}")
            if 'speed_bytes_per_sec' in metrics['git_clone']:
                stats = self._calculate_statistics(metrics['git_clone']['speed_bytes_per_sec'])
                print(f"  Speed: {self._format_speed(stats['mean'])} ± {self._format_speed(stats['std_dev'])}")
    
    def run_multiple_benchmarks(self, num_runs: int = 5, selected_tests=None):
        """Run benchmark suite multiple times and aggregate results

        Args:
            num_runs: Number of times to run the benchmark suite
            selected_tests: Optional list of test categories to run
        """
        print("\n" + "=" * 70)
        print(f"RUNNING {num_runs} BENCHMARK ITERATIONS")
        print("=" * 70)

        for i in range(num_runs):
            print(f"\n{'#' * 70}")
            print(f"# RUN {i + 1} of {num_runs}")
            print(f"{'#' * 70}\n")

            # Drop filesystem caches before each run for consistent results
            self._drop_caches()

            self.setup()
            run_results = self.run_benchmark_suite(selected_tests=selected_tests)
            self.all_runs.append(run_results)
            
            # Print summary for this run
            self._print_summary()
            
            print(f"\nCompleted run {i + 1}/{num_runs}")
        
        # Print aggregated statistics
        self._print_aggregated_results()
        
        # Save all results
        self._save_all_results()
    
    def _save_all_results(self):
        """Save all run results to JSON file"""
        output_file = self.working_dir / f"benchmark_results_{self.name}.json"
        
        # Calculate aggregated statistics
        aggregated_stats = {}
        
        if self.all_runs:
            # Collect all metrics from all runs
            metrics = {}
            
            for run_results in self.all_runs:
                for test_name, test_data in run_results.items():
                    if test_name not in metrics:
                        metrics[test_name] = {}
                    
                    for metric_name, value in test_data.items():
                        if isinstance(value, (int, float)):
                            if metric_name not in metrics[test_name]:
                                metrics[test_name][metric_name] = []
                            metrics[test_name][metric_name].append(value)
            
            # Calculate statistics for each metric
            for test_name, test_metrics in metrics.items():
                aggregated_stats[test_name] = {}
                for metric_name, values in test_metrics.items():
                    stats = self._calculate_statistics(values)
                    aggregated_stats[test_name][metric_name] = {
                        'mean': stats['mean'],
                        'std_dev': stats['std_dev'],
                        'min': min(values),
                        'max': max(values),
                        'values': values
                    }
        
        results_with_metadata = {
            'name': self.name,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'test_directory': str(self.test_dir.absolute()),
            'num_runs': len(self.all_runs),
            'aggregated_statistics': aggregated_stats,
            'all_runs': self.all_runs
        }
        
        with open(output_file, 'w') as f:
            json.dump(results_with_metadata, f, indent=2)
        
        print(f"\n\nDetailed results from all runs saved to: {output_file}")
    
def main():
    import sys
    import argparse

    # Configure the amount of data per test (in GB)
    data_size_gb = 1.0
    num_runs = 5  # Number of full benchmark suite iterations

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='File I/O Performance Benchmark',
        epilog='Examples:\n'
               '  %(prog)s                           # Run all tests\n'
               '  %(prog)s --tests pip               # Run only pip test\n'
               '  %(prog)s --tests pip npm           # Run pip and npm tests\n'
               '  %(prog)s --tests seq_write seq_read  # Run sequential tests only\n',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('test_name', nargs='?', default='default',
                        help='Name for this test run (default: "default")')
    parser.add_argument('--working-folder', '-w', default='./',
                        help='Working folder where tests will run (default: "./")')
    parser.add_argument('--tests', '-t', nargs='+', choices=[
                            'seq_write', 'seq_read', 'rand_write', 'rand_read',
                            'metadata', 'npm', 'pip', 'git'
                        ],
                        help='Select specific tests to run. Available tests: '
                             'seq_write, seq_read, rand_write, rand_read, '
                             'metadata, npm, pip, git. If not specified, all tests run.')
    parser.add_argument('--runs', '-r', type=int, default=5,
                        help='Number of benchmark iterations to run (default: 5)')

    args = parser.parse_args()

    print(f"Test name: {args.test_name}")
    print(f"Working folder: {Path(args.working_folder).resolve()}")
    if args.tests:
        print(f"Selected tests: {', '.join(args.tests)}")
    else:
        print("Running all tests")

    benchmark = FileIOBenchmark(data_size_gb=data_size_gb, name=args.test_name, working_dir=args.working_folder)
    benchmark.run_multiple_benchmarks(num_runs=args.runs, selected_tests=args.tests)
    print("\n" + "=" * 70)
    print("All benchmarks complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
