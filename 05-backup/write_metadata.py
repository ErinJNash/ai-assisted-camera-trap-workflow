#!/usr/bin/env python3
"""
write_metadata.py
=================
Writes verified species tags from a Timelapse export back into the image files'
metadata, so the identification travels with the image itself.

Reads a Timelapse export (.csv or .xlsx), builds each image's full path from its
RelativePath + File columns, and writes the Species value into the images'
Keywords AND Subject metadata fields using exiftool. All edits for a run are
sent to exiftool in ONE invocation (via an argument file), so tagging hundreds
of thousands of images is fast.

This is a worked example from one camera trap workflow. Edit the USER SETTINGS
block (or pass the equivalent command-line flags) before using it on your data.

WHAT IT EXPECTS
---------------
- A Timelapse export with at least these columns: RelativePath, File, Species
  (column names are configurable in USER SETTINGS).
- The image files on disk, under a base folder, organised so that
  base / RelativePath / File  points to each image.
- exiftool installed and on PATH (https://exiftool.org). Check with:
      exiftool -ver

USAGE
-----
    python write_metadata.py timelapse_export.csv \\
        --image-base /path/to/folder/containing/the/images

    # preview without changing any files:
    python write_metadata.py timelapse_export.xlsx \\
        --image-base /path/to/images --dry-run

By default the script OVERWRITES the original image files in place (the tag is
written into the existing file). Pass --keep-originals to have exiftool leave
a "<name>_original" backup of each changed file instead.

Requirements (auto-installed on first run if missing): pandas, openpyxl
(openpyxl is only needed for .xlsx input). exiftool must be installed separately.

##############################################################################
#  >>> USER SETTINGS: EDIT THESE IF YOU RE-USE THIS SCRIPT <<<
##############################################################################
"""

import sys
import os
import subprocess
import argparse
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Dependency auto-install (pandas; openpyxl only if reading .xlsx)
# ---------------------------------------------------------------------------
def _ensure_deps(need_xlsx=False):
    needed = {"pandas": "pandas"}
    if need_xlsx:
        needed["openpyxl"] = "openpyxl"
    missing = []
    for mod, pkg in needed.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)} ...")
        cmd = [sys.executable, "-m", "pip", "install", *missing,
               "--break-system-packages", "--quiet"]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   *missing, "--quiet"])
        print("  done.")


##############################################################################
#  USER SETTINGS  -----------------------------------------------------------
#  >>> EDIT THESE when you re-use the script on a new batch / new computer <<<
##############################################################################

# Base folder that the export's RelativePath values are relative to — i.e. the
# folder that CONTAINS your station/deployment image folders.
# Leave "" and pass --image-base on the command line, or set it here.
#   >>> SET THIS (or pass --image-base) <<<
IMAGE_BASE_DIR = ""

# Column names in the Timelapse export. Change these only if your export uses
# different headers.
COL_RELATIVE_PATH = "RelativePath"
COL_FILE          = "File"
COL_SPECIES       = "Species"

# Metadata fields to write the species into. Both are written by default.
#   >>> EDIT if you only want one of them <<<
METADATA_FIELDS = ["Keywords", "Subject"]

# If a species cell is blank, skip that row (True) or write an empty tag (False).
SKIP_BLANK_SPECIES = True

##############################################################################
#  END USER SETTINGS  -------------------------------------------------------
##############################################################################


def load_table(path):
    """Read a Timelapse export as a list of dict rows. Supports .csv and .xlsx."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        _ensure_deps(need_xlsx=False)
        import pandas as pd
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif suffix in (".xlsx", ".xlsm"):
        _ensure_deps(need_xlsx=True)
        import pandas as pd
        df = pd.read_excel(path, dtype=str).fillna("")
    else:
        print(f"Error: unsupported input type '{suffix}'. Use .csv or .xlsx.")
        sys.exit(1)
    return df.to_dict("records"), list(df.columns)


def build_full_path(base, relative_path, filename):
    """base / RelativePath / File -> absolute path, normalising backslashes."""
    rel = (relative_path or "").replace("\\", "/").strip()
    fname = (filename or "").strip()
    if not fname:
        return None
    parts = [p for p in rel.split("/") if p] + [fname]
    return os.path.join(base, *parts)


def main():
    parser = argparse.ArgumentParser(
        description="Write Timelapse Species tags into image metadata via exiftool.")
    parser.add_argument("input", help="Timelapse export (.csv or .xlsx)")
    parser.add_argument("--image-base", help="Override IMAGE_BASE_DIR from USER SETTINGS")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be tagged without changing any files")
    parser.add_argument("--keep-originals", action="store_true",
                        help="Keep exiftool '<name>_original' backups (default: overwrite in place)")
    args = parser.parse_args()

    base = args.image_base if args.image_base else IMAGE_BASE_DIR
    if not base:
        print("Error: no image base directory set. Pass --image-base or set")
        print("       IMAGE_BASE_DIR in USER SETTINGS.")
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    # Check exiftool is available early (unless this is a dry run).
    if not args.dry_run:
        try:
            subprocess.run(["exiftool", "-ver"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("Error: exiftool not found on PATH. Install it from")
            print("       https://exiftool.org and try again (check: exiftool -ver).")
            sys.exit(1)

    rows, columns = load_table(input_path)
    for needed in (COL_RELATIVE_PATH, COL_FILE, COL_SPECIES):
        if needed not in columns:
            print(f"Error: expected column '{needed}' not found in {input_path.name}.")
            print(f"       Columns present: {columns}")
            print("       Adjust the COL_* names in USER SETTINGS if your export differs.")
            sys.exit(1)

    # Build the work list
    to_tag = []       # (full_path, species)
    n_blank = 0
    n_nofile = 0
    n_missing = 0
    for row in rows:
        species = (row.get(COL_SPECIES) or "").strip()
        if not species and SKIP_BLANK_SPECIES:
            n_blank += 1
            continue
        full = build_full_path(base, row.get(COL_RELATIVE_PATH), row.get(COL_FILE))
        if full is None:
            n_nofile += 1
            continue
        if not os.path.exists(full):
            n_missing += 1
            print(f"  missing file (skipped): {full}")
            continue
        to_tag.append((full, species))

    print(f"\nRows read:            {len(rows):,}")
    print(f"Blank species:        {n_blank:,} (skipped)" if SKIP_BLANK_SPECIES else "")
    print(f"No filename:          {n_nofile:,} (skipped)")
    print(f"File not found:       {n_missing:,} (skipped)")
    print(f"Images to tag:        {len(to_tag):,}")
    print(f"Metadata fields:      {', '.join(METADATA_FIELDS)}")

    if not to_tag:
        print("\nNothing to tag. Done.")
        return

    if args.dry_run:
        print("\n--dry-run: no files changed. First few that WOULD be tagged:")
        for full, sp in to_tag[:10]:
            print(f"    {sp:<28} -> {full}")
        if len(to_tag) > 10:
            print(f"    ... and {len(to_tag) - 10:,} more")
        return

    # ---- Build ONE exiftool argument file for the whole batch -------------
    # exiftool reads newline-separated arguments from the file given after -@.
    # For each image we emit the tag assignments then the file path, so all
    # edits run in a single exiftool process (fast).
    overwrite_arg = "-overwrite_original" if not args.keep_originals else None

    with tempfile.NamedTemporaryFile("w", suffix=".args", delete=False,
                                     encoding="utf-8") as af:
        argfile = af.name
        for full, species in to_tag:
            for field in METADATA_FIELDS:
                # Use the assignment form so multiple species (comma-separated in
                # the cell) become a single keyword string; edit here if you want
                # to split them into separate list items instead.
                af.write(f"-{field}={species}\n")
            if overwrite_arg:
                af.write(f"{overwrite_arg}\n")
            af.write(f"{full}\n")
            af.write("-execute\n")   # process each file as its own command

    print(f"\nTagging {len(to_tag):,} images with exiftool (single batch)...")
    try:
        # -common_args isn't needed; -@ argfile drives everything. -q quiets
        # per-file chatter; remove -q if you want exiftool's own progress.
        result = subprocess.run(["exiftool", "-q", "-@", argfile],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print("exiftool reported errors:")
            print(result.stderr[:2000])
        else:
            print("  done.")
    finally:
        try:
            os.unlink(argfile)
        except OSError:
            pass

    print(f"\nFinished. Tagged {len(to_tag):,} images "
          f"into {', '.join(METADATA_FIELDS)}.")
    if args.keep_originals:
        print("Originals kept as '<name>_original' beside each changed file.")
    else:
        print("Originals overwritten in place.")


if __name__ == "__main__":
    main()
