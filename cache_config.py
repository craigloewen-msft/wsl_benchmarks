#!/usr/bin/env python3
"""
Cache configuration for benchmark tests.

This file contains the definitions of packages and dependencies used
for cache setup. It is kept separate so that Docker can cache the
setup layer even when benchmark parameters change.
"""

# Pip packages to use for offline cache benchmark
PIP_PACKAGES = [
    'requests',
    'flask',
    'click',
    'jinja2',
    'urllib3',
    'certifi',
    'charset-normalizer',
    'idna',
    'werkzeug',
    'markupsafe',
    'itsdangerous',
    'blinker',
    'torch',  # CPU version of PyTorch
]

PIP_EXTRA_INDEX_URL = 'https://download.pytorch.org/whl/cpu'  # For CPU-only PyTorch

# NPM packages to use for offline cache benchmark
NPM_PACKAGE_JSON = {
    "name": "benchmark-test",
    "version": "1.0.0",
    "dependencies": {
        "express": "4.18.2",
        "lodash": "4.17.21",
        "axios": "1.6.0",
        "react": "18.2.0",
        "react-dom": "18.2.0",
        "@angular/core": "17.0.0",
        "@angular/common": "17.0.0",
        "@angular/platform-browser": "17.0.0",
        "vue": "3.3.8",
        "next": "14.0.3",
        "typescript": "5.3.2",
        "webpack": "5.89.0",
        "eslint": "8.54.0",
        "jest": "29.7.0",
        "@babel/core": "7.23.5",
        "prettier": "3.1.0",
        "tailwindcss": "3.3.5"
    }
}

# Git repositories to clone for offline cache benchmark
# Using popular open-source repos with lots of files for a good benchmark
GIT_REPOS = [
    {
        'name': 'vscode',
        'url': 'https://github.com/microsoft/vscode.git',
        'depth': 1,  # Shallow clone to save space but still get all files
    },
]

# Default cache directory name
CACHE_DIR_NAME = "benchmark_cache"
