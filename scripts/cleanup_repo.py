#!/usr/bin/env python3
"""
Repository cleanup utility.
Removes generated artefacts and caches while preserving tracked files and data outputs.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Whitelist: directories and patterns that should NEVER be deleted
WHITELIST_DIRS = {
    '.git',
    '.github',
    '.venv',
    'venv',
    'app',
    'data',
    'docs',
    'scripts',
    'src',
    'tests',
}

WHITELIST_FILES = {
    '.env',
    '.env.example',
    '.gitignore',
    '.pre-commit-config.yaml',
    'Makefile',
    'README.md',
    'CHANGELOG.md',
    'paths.py',
    'pyproject.toml',
    'requirements.txt',
    'requirements.lock',
    'run_pipeline.py',
    'setup.sh',
    'verify_fixes.sh',
}

# Patterns to clean (generated artefacts)
CLEAN_PATTERNS = {
    '__pycache__',
    '.pytest_cache',
    '.ruff_cache',
    '.mypy_cache',
    '.DS_Store',
}


def find_cleanable_paths(root: Path) -> list[Path]:
    """Find paths that should be cleaned."""
    cleanable = []

    for item in root.rglob('*'):
        # Skip whitelisted directories
        if any(parent.name in WHITELIST_DIRS for parent in item.parents):
            continue
        if item.name in WHITELIST_DIRS:
            continue

        # Skip whitelisted files at root
        if item.is_file() and item.parent == root and item.name in WHITELIST_FILES:
            continue

        # Skip data outputs (CSV, JSON in data/)
        if item.is_file() and 'data' in [p.name for p in item.parents]:
            if item.suffix in {'.csv', '.json'}:
                continue

        # Check if matches clean patterns
        if item.name in CLEAN_PATTERNS or item.suffix in {'.pyc', '.pyo', '.tmp'}:
            cleanable.append(item)

    return cleanable


def main():
    parser = argparse.ArgumentParser(description='Clean generated artefacts from repository')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Show what would be cleaned')
    parser.add_argument('--clean', action='store_true', help='Actually perform the cleanup')
    args = parser.parse_args()

    dry_run = not args.clean
    repo_root = Path(__file__).parent.parent

    if dry_run:
        print("🔍 DRY-RUN MODE: Scanning for cleanable artefacts...")
    else:
        print("🧹 CLEANUP MODE: Removing generated artefacts...")

    cleanable = find_cleanable_paths(repo_root)

    if not cleanable:
        print("✨ Repository is already clean!")
        return 0

    dirs_to_remove = [p for p in cleanable if p.is_dir()]
    files_to_remove = [p for p in cleanable if p.is_file()]

    print(f"Found {len(dirs_to_remove)} directories and {len(files_to_remove)} files to clean\n")

    for path in sorted(cleanable):
        if dry_run:
            print(f"[WOULD REMOVE] {path}")
        else:
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                print(f"✓ Removed: {path}")
            except Exception as e:
                print(f"✗ Error removing {path}: {e}", file=sys.stderr)

    if dry_run:
        print("\n💡 To actually clean, run: python scripts/cleanup_repo.py --clean")
        return 1 if cleanable else 0
    else:
        print("\n✅ Cleanup complete!")
        return 0


if __name__ == '__main__':
    sys.exit(main())
