#!/usr/bin/env python3
"""
Root Directory Cleanup Script

Removes duplicate files from the root directory that have been properly
organized into subdirectories (src/, app/, scripts/, tests/).

SAFETY: Only deletes root files if the corresponding subdirectory version exists.
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))


# Mapping of root files to their new locations
MIGRATION_MAP: dict[str, str] = {
    # Scripts moved to scripts/
    "main.py": "scripts/main.py",
    "analysis.py": "scripts/analysis.py",
    "check_models.py": "scripts/check_models.py",

    # Core modules moved to src/
    "taxonomy.py": "src/taxonomy.py",
    "enrich_companies.py": "src/enrich_companies.py",
    "company_classifier.py": "src/company_classifier.py",

    # UI moved to app/
    "dashboard.py": "app/dashboard.py",

    # Tests moved to tests/
    "test_dedupe.py": "tests/test_dedupe.py",
    "test_strengths.py": "tests/test_strengths.py",
}

# Junk files to always remove (no safety check needed)
JUNK_FILES = [
    "Archive.zip",
    ".DS_Store",
]

def check_duplicates(root: Path) -> list[tuple[Path, Path, bool]]:
    """
    Check for duplicate files in root that exist in subdirectories.

    Returns:
        List of (root_file, subfolder_file, safe_to_delete) tuples
    """
    duplicates = []

    for root_filename, subfolder_path in MIGRATION_MAP.items():
        root_file = root / root_filename
        subfolder_file = root / subfolder_path

        # Check if both exist
        root_exists = root_file.exists()
        subfolder_exists = subfolder_file.exists()

        # Only safe to delete if subfolder version exists
        safe_to_delete = root_exists and subfolder_exists

        if root_exists:
            duplicates.append((root_file, subfolder_file, safe_to_delete))

    return duplicates

def check_junk(root: Path) -> list[Path]:
    """Find junk files in root directory."""
    junk = []
    for filename in JUNK_FILES:
        file_path = root / filename
        if file_path.exists():
            junk.append(file_path)
    return junk

def main():
    """Execute root cleanup."""
    root = Path(__file__).resolve().parent.parent

    print("=" * 70)
    print("ROOT DIRECTORY CLEANUP SCRIPT")
    print("=" * 70)
    print()
    print(f"Working directory: {root}")
    print()

    # Check for duplicates
    duplicates = check_duplicates(root)
    junk_files = check_junk(root)

    # Filter to only safe-to-delete duplicates
    safe_duplicates = [(r, s, safe) for r, s, safe in duplicates if safe]
    unsafe_duplicates = [(r, s, safe) for r, s, safe in duplicates if not safe]

    # Summary
    print("CLEANUP PLAN:")
    print("-" * 70)
    print(f"  • Duplicate root files (safe to delete): {len(safe_duplicates)}")
    print(f"  • Duplicate root files (UNSAFE - no subfolder version): {len(unsafe_duplicates)}")
    print(f"  • Junk files: {len(junk_files)}")
    print()

    total_to_delete = len(safe_duplicates) + len(junk_files)

    if total_to_delete == 0:
        print("✅ Root directory is already clean! Nothing to delete.")
        print()
        print("Current root Python files:")
        root_py_files = sorted([f.name for f in root.glob("*.py")])
        for filename in root_py_files:
            print(f"  ✓ {filename}")
        return

    # Show what will be deleted
    if safe_duplicates:
        print("SAFE TO DELETE (subfolder version exists):")
        print("-" * 70)
        for root_file, subfolder_file, _ in safe_duplicates:
            print(f"  ✓ {root_file.name}")
            print(f"      ROOT: {root_file}")
            print(f"      SUBFOLDER: {subfolder_file} {'✓ EXISTS' if subfolder_file.exists() else '✗ MISSING'}")
            print()

    if unsafe_duplicates:
        print("⚠️  UNSAFE TO DELETE (no subfolder version):")
        print("-" * 70)
        for root_file, subfolder_file, _ in unsafe_duplicates:
            print(f"  ⚠️  {root_file.name}")
            print(f"      ROOT: {root_file}")
            print(f"      EXPECTED: {subfolder_file} (DOES NOT EXIST)")
            print()

    if junk_files:
        print("JUNK FILES TO DELETE:")
        print("-" * 70)
        for junk_file in junk_files:
            print(f"  ✓ {junk_file.name}")
            print(f"      PATH: {junk_file}")
            print()

    # Execute deletion
    print("EXECUTING CLEANUP:")
    print("-" * 70)

    deleted_count = 0
    error_count = 0

    # Delete safe duplicates
    for root_file, subfolder_file, _ in safe_duplicates:
        try:
            root_file.unlink()
            print(f"✓ Deleted: {root_file.name} (copy exists at {subfolder_file.relative_to(root)})")
            deleted_count += 1
        except Exception as e:
            print(f"✗ Failed to delete {root_file.name}: {e}")
            error_count += 1

    # Delete junk files
    for junk_file in junk_files:
        try:
            junk_file.unlink()
            print(f"✓ Deleted: {junk_file.name} (junk file)")
            deleted_count += 1
        except Exception as e:
            print(f"✗ Failed to delete {junk_file.name}: {e}")
            error_count += 1

    print()

    # Final verification
    print("=" * 70)
    print("CLEANUP SUMMARY")
    print("=" * 70)
    print(f"✓ Files deleted successfully: {deleted_count}")
    if error_count > 0:
        print(f"✗ Files failed to delete: {error_count}")
    if unsafe_duplicates:
        print(f"⚠️  Files skipped (no subfolder version): {len(unsafe_duplicates)}")
    print()

    # Show final root state
    print("FINAL ROOT DIRECTORY STATE:")
    print("-" * 70)
    print("Python files remaining in root:")
    root_py_files = sorted([f.name for f in root.glob("*.py")])
    if root_py_files:
        for filename in root_py_files:
            print(f"  ✓ {filename}")
    else:
        print("  (no .py files in root)")

    print()
    print("=" * 70)
    if error_count == 0 and deleted_count > 0:
        print("✅ CLEANUP COMPLETE - ROOT DIRECTORY IS NOW CLEAN")
    elif deleted_count == 0:
        print("✅ ROOT DIRECTORY WAS ALREADY CLEAN")
    else:
        print("⚠️  CLEANUP COMPLETED WITH ERRORS")
    print("=" * 70)

if __name__ == "__main__":
    main()
