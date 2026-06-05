#!/usr/bin/env python3
"""
Data Unification Script

Moves all files from outputs/ to data/ and removes the outputs/ directory.
This ensures Streamlit Cloud deployment has stable access to all data files.

Run this ONCE to migrate from the old structure to the new unified structure.
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import shutil


def find_files_to_move(outputs_dir: Path, data_dir: Path) -> list[tuple[Path, Path]]:
    """
    Find all files in outputs/ that need to be moved to data/.

    Returns:
        List of (source, destination) tuples
    """
    if not outputs_dir.exists():
        return []

    moves = []
    for file_path in outputs_dir.iterdir():
        if file_path.is_file():
            dest_path = data_dir / file_path.name
            moves.append((file_path, dest_path))

    return moves

def main():
    """Execute the data unification."""
    root = Path(__file__).resolve().parent.parent
    outputs_dir = root / "outputs"
    data_dir = root / "data"

    print("=" * 70)
    print("DATA UNIFICATION SCRIPT")
    print("=" * 70)
    print()
    print(f"Source directory: {outputs_dir}")
    print(f"Destination directory: {data_dir}")
    print()

    # Ensure data/ exists
    data_dir.mkdir(exist_ok=True)

    # Find files to move
    files_to_move = find_files_to_move(outputs_dir, data_dir)

    if not files_to_move:
        if not outputs_dir.exists():
            print("✓ outputs/ directory does not exist")
            print("✓ Data is already unified in data/")
        else:
            print("✓ outputs/ directory is empty")
            print("✓ Removing empty outputs/ directory...")
            try:
                outputs_dir.rmdir()
                print("✓ Removed outputs/")
            except Exception as e:
                print(f"⚠️  Could not remove outputs/: {e}")

        print()
        print("=" * 70)
        print("✅ DATA ALREADY UNIFIED - NOTHING TO DO")
        print("=" * 70)
        return

    # Show migration plan
    print("MIGRATION PLAN:")
    print("-" * 70)
    for src, dst in files_to_move:
        status = "⚠️  OVERWRITE" if dst.exists() else "➜ MOVE"
        print(f"  {status} {src.name}")
        print(f"         FROM: {src}")
        print(f"         TO:   {dst}")
        print()

    print(f"Total files to move: {len(files_to_move)}")
    print()

    # Execute migration
    print("EXECUTING MIGRATION:")
    print("-" * 70)

    moved_count = 0
    error_count = 0

    for src, dst in files_to_move:
        try:
            # Move file (will overwrite if exists)
            shutil.move(str(src), str(dst))
            print(f"✓ Moved: {src.name} → {dst}")
            moved_count += 1
        except Exception as e:
            print(f"✗ Failed to move {src.name}: {e}")
            error_count += 1

    print()

    # Remove outputs/ directory if now empty
    if outputs_dir.exists() and not list(outputs_dir.iterdir()):
        print("Removing empty outputs/ directory...")
        try:
            outputs_dir.rmdir()
            print("✓ Removed outputs/")
        except Exception as e:
            print(f"⚠️  Could not remove outputs/: {e}")
    elif outputs_dir.exists():
        remaining = list(outputs_dir.iterdir())
        print(f"⚠️  outputs/ still contains {len(remaining)} items:")
        for item in remaining:
            print(f"   - {item.name}")

    # Final summary
    print()
    print("=" * 70)
    print("MIGRATION SUMMARY")
    print("=" * 70)
    print(f"✓ Files moved successfully: {moved_count}")
    if error_count > 0:
        print(f"✗ Files failed to move: {error_count}")
    print(f"✓ outputs/ removed: {not outputs_dir.exists()}")
    print()

    # Verification
    print("VERIFICATION:")
    print("-" * 70)
    print("Files now in data/:")

    data_files = sorted([f.name for f in data_dir.iterdir() if f.is_file()])
    for filename in data_files:
        print(f"  ✓ {filename}")

    print()
    print("=" * 70)
    if error_count == 0 and not outputs_dir.exists():
        print("✅ MIGRATION COMPLETE - ALL DATA NOW IN data/")
    elif error_count > 0:
        print("⚠️  MIGRATION COMPLETED WITH ERRORS")
    else:
        print("⚠️  MIGRATION COMPLETE BUT outputs/ STILL EXISTS")
    print("=" * 70)

if __name__ == "__main__":
    main()
