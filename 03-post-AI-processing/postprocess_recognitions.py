#!/usr/bin/env python3
"""
postprocess_recognitions.py
=======================
Reads a MegaDetector / SpeciesNet recognition JSON directly (streamed, so it
handles multi-GB files), reads each image's timestamp from its EXIF metadata,
groups images into temporal "visits" per camera, and writes a Timelapse-ready
CSV with one row per image.

This is a worked example from one camera trap workflow. The species lists, label
groupings, and thresholds below are EXAMPLES tied to one project's fauna (south-
eastern Australia) — treat them as a starting point and edit them for your own
study area before relying on the output.

WHAT THE SCRIPT EXPECTS
-----------------------
- A recognition JSON in MegaDetector output format (with "images",
  "detection_categories", and "classification_categories" keys).
- Images organised on disk as  STATION/DEPLOYMENT/IMAGE.JPG  (any depth is read,
  but the first two path parts are treated as station and deployment).
- A Timelapse template (.tdb) whose field list the import CSV is matched to.

WHAT IT DOES
------------
1. Populates four SINGLE recognition fields from the highest-confidence
   detection box in each image:
       Detection                <- that box's detection category (animal/person/vehicle)
       DetectionConfidence      <- that box's detection confidence
       Recognitions             <- that box's top species classification label
       ClassificationConfidence <- that box's top classification confidence
   (The full per-detection Det1_*..Det4_* columns are STILL written to the CSV
    as an archive; you just don't have to import them into Timelapse.)

2. Temporal consensus correction. Images are grouped into visits per camera
   (station+deployment), split wherever the gap between consecutive images
   exceeds VISIT_GAP_SECONDS. Within a visit, if one species dominates
   (>= CONSENSUS_PCT_MIN of labelled images), outliers are corrected to it:
       - outlier confidence  < OUTLIER_OVERRIDE_CONF  -> relabel, no review
       - outlier confidence >= OUTLIER_OVERRIDE_CONF  -> relabel, FLAG review
       - outlier is 'false detection' inside a species visit -> relabel, FLAG review
       - outlier is a PRIORITY species -> relabel, ALWAYS FLAG review
   Timestamps come from EXIF, so this runs before Timelapse is opened.

3. Multi-species visits still set HasMultipleSpecies=TRUE and force review.

USAGE
-----
    python postprocess_recognitions.py recognitions.json \\
        --image-base /path/to/folder/containing/station/folders \\
        --template   /path/to/your_template.tdb \\
        -o           output.csv

If --image-base / --template / -o are omitted, the script falls back to the
values in the USER SETTINGS block below (all blank by default). At minimum you
must provide the input JSON and an image base directory for the EXIF-based
consensus step to run.

Requirements (auto-installed on first run if missing): ijson, pandas, Pillow

##############################################################################
#  >>> USER SETTINGS: EDIT THESE IF YOU RE-USE THIS SCRIPT <<<
#  Everything you may need to change for a new batch is in the USER SETTINGS
#  block just below the imports. Search for "USER SETTINGS".
##############################################################################
"""

import sys
import os
import re
import subprocess
import argparse
import sqlite3
from pathlib import Path
from collections import Counter, defaultdict


# ---------------------------------------------------------------------------
# Dependency auto-install (ijson, pandas, Pillow)
# ---------------------------------------------------------------------------
def _ensure_deps():
    needed = {"ijson": "ijson", "pandas": "pandas", "PIL": "Pillow"}
    missing = []
    for mod, pkg in needed.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing packages: {', '.join(missing)} ...")
        # --break-system-packages is needed on newer macOS/Homebrew Python;
        # it is harmless on setups that don't require it.
        cmd = [sys.executable, "-m", "pip", "install", *missing,
               "--break-system-packages", "--quiet"]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            # Retry without the flag for environments that reject it
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   *missing, "--quiet"])
        print("  done.")

_ensure_deps()

import ijson                      # noqa: E402
import pandas as pd               # noqa: E402
from PIL import Image             # noqa: E402


##############################################################################
#  USER SETTINGS  -----------------------------------------------------------
#  >>> EDIT THESE when you re-use the script on a new batch / new computer <<<
##############################################################################

# Base folder that the JSON's "file" paths are relative to.
# The JSON stores paths like "STATION_01/DEPLOYMENT_01/IMG_0001.JPG", so
# IMAGE_BASE_DIR must be the folder that CONTAINS the station folders.
# Leave "" and pass --image-base on the command line, or set it here.
#   >>> SET THIS (or pass --image-base) to wherever the image folders live <<<
IMAGE_BASE_DIR = ""

# Default output CSV (the FULL ARCHIVE). If left "", the script writes the CSV
# next to the input JSON, named "<input-stem>_inferred.csv". A second "_import"
# CSV (template-matched columns only) is written alongside it automatically.
#   >>> Usually leave blank; override per run with -o if you want <<<
DEFAULT_OUTPUT = ""

# Path to your Timelapse template (.tdb). The script reads the template's
# field list from this file and writes the "_import" CSV with EXACTLY those
# columns, in the template's order - so the import file always matches the
# template and Timelapse won't reject it. If left "" the import CSV is
# skipped (only the full archive is written).
#   >>> SET THIS (or pass --template) to your template path <<<
TEMPLATE_TDB_PATH = ""

# --- Temporal consensus settings -------------------------------------------
VISIT_GAP_SECONDS      = 120    # >120 s between consecutive images = new visit
CONSENSUS_PCT_MIN      = 0.75   # dominant species must be >=75% of labelled imgs
CONSENSUS_CONF_MIN     = 0.60   # dominant species mean confidence must be >= this
OUTLIER_OVERRIDE_CONF  = 0.79   # outliers at/above this conf get relabel + review;
                                # below it, relabel silently (no review)

# An animal detection box is only allowed to "lead" an image (become the primary
# InferredTag ahead of a person/vehicle box) if its confidence is at least this.
# This stops a near-zero-confidence animal box (noise) from overriding a
# confident person/vehicle detection. Genuine animal detections clear it easily.
#   >>> RAISE/LOWER this to match the detector threshold used for the JSON <<<
ANIMAL_LEAD_MIN_CONF   = 0.20

# --- Confidence rating thresholds (reused from earlier versions) -----------
HIGH_CONF_THRESHOLD = 0.80      # accept a species classification directly
MEDIUM_CONF_MIN     = 0.60      # lower bound for a "Medium" rating
AMBIGUITY_GAP       = 0.20      # top-vs-2nd gap below this = ambiguous = review

MAX_SLOTS = 4                   # detection slots written to the CSV archive

# --- Label remapping (lowercase keys -> lowercase values) ------------------
# EXAMPLE groupings from one project — replace with your own. Use this to roll
# hard-to-separate classes up into a coarser label (here, lumping some birds).
#   >>> EDIT / CLEAR THESE for your own species <<<
LABEL_REMAP = {
    "australian raven": "bird spp",
    "grey currawong":   "currawong spp",
    "pied currawong":   "currawong spp",
}

# Species that ALWAYS require human review (and are never silently overridden).
# EXAMPLE list from one south-eastern Australian project — it is a fingerprint
# of that study's pest and priority species and will NOT match your fauna.
#   >>> REPLACE THIS LIST with your own priority/pest species (lowercase) <<<
PRIORITY_REVIEW_SPECIES = {
    "domestic cat feral", "red fox", "sambar deer", "red deer", "fallow deer",
    "deer", "bush rat", "black rat", "swamp rat", "broad-toothed rat",
    "house mouse", "white-footed dunnart", "swamp antechinus",
    "mainland dusky antechinus", "agile antechinus", "spot-tailed quoll",
    "southern long-nosed bandicoot", "southern brown bandicoot",
    "long-nosed potoroo", "eastern pygmy possum",
}

##############################################################################
#  END USER SETTINGS  -------------------------------------------------------
##############################################################################


# Fixed internal constants (you normally won't change these)
DETECTION_ONLY_LABELS = {"person", "vehicle"}
NON_SPECIES           = {"unidentified animal", "false detection"} | DETECTION_ONLY_LABELS
SUPPRESSED_LABEL      = "False Detection (suppressed)"
PRESERVE_CASE_TAGS    = {"bird spp": "Bird spp", "currawong spp": "Currawong spp"}
GENERIC_ANIMAL        = "animal"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def remap(label):
    if label is None:
        return None
    return LABEL_REMAP.get(label, label)


def title_case_tag(val):
    """'black-tailed wallaby' -> 'Black-tailed Wallaby', preserving special tags."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return val
    s = str(val)
    if s == SUPPRESSED_LABEL:
        return s
    if s.lower() in PRESERVE_CASE_TAGS:
        return PRESERVE_CASE_TAGS[s.lower()]
    titled = s.title()
    return re.sub(r'(?<=-)[A-Z]', lambda m: m.group(0).lower(), titled)


def split_file_path(file_str):
    """'STATION_01/DEPLOYMENT_01/IMG_0001.JPG' -> ('STATION_01\\DEPLOYMENT_01', 'IMG_0001.JPG')."""
    if not file_str:
        return '', ''
    parts = re.split(r'[/\\]+', str(file_str))
    fname = parts[-1]
    rel = '\\'.join(parts[:-1])
    return rel, fname


def station_and_deployment(relative_path):
    """'STATION_01\\DEPLOYMENT_01' -> ('STATION_01', 'DEPLOYMENT_01')."""
    if not relative_path:
        return '', ''
    parts = [p for p in re.split(r'[/\\]+', relative_path) if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ''
    return '', ''


def conf_rating(conf):
    if conf is None:
        return 'Low'
    if conf >= 0.90:
        return 'High'
    if conf >= HIGH_CONF_THRESHOLD:
        return 'Medium'
    if conf >= MEDIUM_CONF_MIN:
        return 'Medium'
    return 'Low'


def _fmt(x):
    if x is None:
        return ''
    return f'{float(x):.4f}'


def _name(label):
    if label is None:
        return ''
    return title_case_tag(label)


# ---------------------------------------------------------------------------
# EXIF timestamp reading
# ---------------------------------------------------------------------------

# EXIF tag 36867 = DateTimeOriginal, 306 = DateTime
_EXIF_DT_TAGS = (36867, 306)

def read_exif_datetime(full_path):
    """
    Return a datetime for the image, read from EXIF, or None if unavailable.
    Header-only read (Pillow does not decode pixels for getexif()).
    """
    try:
        with Image.open(full_path) as img:
            exif = img.getexif()
            if not exif:
                return None
            for tag in _EXIF_DT_TAGS:
                val = exif.get(tag)
                if val:
                    # EXIF format: 'YYYY:MM:DD HH:MM:SS'
                    s = str(val).strip()
                    try:
                        return pd.to_datetime(s, format='%Y:%m:%d %H:%M:%S')
                    except (ValueError, TypeError):
                        try:
                            return pd.to_datetime(s)   # fallback parse
                        except Exception:
                            return None
    except (FileNotFoundError, OSError):
        return None
    return None


# ---------------------------------------------------------------------------
# Category maps (read from the JSON itself, not hardcoded)
# ---------------------------------------------------------------------------

def load_category_maps(json_path):
    det_map, cls_map = {}, {}
    with open(json_path, 'rb') as f:
        for key, value in ijson.kvitems(f, 'detection_categories'):
            det_map[str(key)] = str(value).strip().lower()
    with open(json_path, 'rb') as f:
        for key, value in ijson.kvitems(f, 'classification_categories'):
            cls_map[str(key)] = str(value).strip().lower()
    if '1' not in det_map:           # MegaDetector convention: 1 = generic animal
        det_map['1'] = GENERIC_ANIMAL
    return det_map, cls_map


# ---------------------------------------------------------------------------
# Per-detection interpretation
# ---------------------------------------------------------------------------

def interpret_detection(det, det_map, cls_map):
    cat       = str(det.get('category', ''))
    det_conf  = det.get('conf')
    det_label = det_map.get(cat, GENERIC_ANIMAL)

    if det_label == 'person':
        det_type = 'person'
    elif det_label == 'vehicle':
        det_type = 'vehicle'
    else:
        det_type = 'animal'

    species = conf = species2 = conf2 = None
    classifications = det.get('classifications') or []
    if classifications:
        top = classifications[0]
        species = remap(cls_map.get(str(top[0]), None))
        conf    = float(top[1])
        if len(classifications) > 1:
            second   = classifications[1]
            species2 = remap(cls_map.get(str(second[0]), None))
            conf2    = float(second[1])
    elif det_type == 'animal':
        if det_label not in (GENERIC_ANIMAL, 'person', 'vehicle'):
            species = remap(det_label)
            conf    = float(det_conf) if det_conf is not None else None
        else:
            species = 'unidentified animal'
            conf    = float(det_conf) if det_conf is not None else None

    gap = (conf - conf2) if (conf is not None and conf2 is not None) else None
    return {
        'det_type': det_type, 'species': species, 'conf': conf,
        'species2': species2, 'conf2': conf2, 'gap': gap,
        'det_conf': float(det_conf) if det_conf is not None else None,
        'is_animal': det_type == 'animal',
    }


# ---------------------------------------------------------------------------
# Pass 1 — per-image inference (independent of neighbours)
# ---------------------------------------------------------------------------

def is_real_species(r):
    return (r['is_animal'] and r['species'] is not None
            and r['species'] not in NON_SPECIES)


def process_image(image, det_map, cls_map):
    """
    Build the per-image record dict (one output row, pre-consensus).
    Also returns intermediate fields needed for the consensus pass.
    """
    file_str   = image.get('file', '')
    detections = image.get('detections') or []
    rel, fname = split_file_path(file_str)
    station, deployment = station_and_deployment(rel)

    recs = [interpret_detection(d, det_map, cls_map) for d in detections]

    # ---- In-image false-detection suppression ----------------------------
    has_conf_real = any(
        is_real_species(r) and r['conf'] is not None and r['conf'] >= HIGH_CONF_THRESHOLD
        for r in recs
    )
    suppressed_any = False
    for r in recs:
        is_weak = ((r['species'] in (None, 'unidentified animal', 'false detection'))
                   and (r['conf'] is None or r['conf'] < HIGH_CONF_THRESHOLD))
        if has_conf_real and is_weak and not is_real_species(r):
            r['suppressed'] = True
            suppressed_any = True
        else:
            r['suppressed'] = False

    # ---- Order: animals-first (confidence-gated), then by confidence -----
    # An animal box leads ONLY if its confidence clears ANIMAL_LEAD_MIN_CONF.
    # A sub-threshold animal box (noise) is demoted below person/vehicle so it
    # can't become the primary ahead of a confident person/vehicle detection.
    def sort_key(r):
        if r['suppressed']:
            prio = 3
        elif r['is_animal']:
            c_anim = r['conf'] if r['conf'] is not None else (r['det_conf'] or 0.0)
            prio = 0 if c_anim >= ANIMAL_LEAD_MIN_CONF else 2   # weak animal -> after person/vehicle
        else:
            prio = 1                                            # person / vehicle
        c = r['conf'] if r['conf'] is not None else (r['det_conf'] or -1.0)
        return (prio, -c)
    recs_sorted = sorted(recs, key=sort_key)

    # ---- Slot columns (CSV archive) --------------------------------------
    row = {}
    for i in range(MAX_SLOTS):
        n = i + 1
        if i < len(recs_sorted):
            r = recs_sorted[i]
            if r['suppressed']:
                row[f'Det{n}_DetType'] = r['det_type']
                row[f'Det{n}_Species'] = SUPPRESSED_LABEL
                row[f'Det{n}_Conf'] = _fmt(r['conf'] if r['conf'] is not None else r['det_conf'])
                row[f'Det{n}_Species2'] = ''
                row[f'Det{n}_Conf_Species2'] = ''
                row[f'Det{n}_Gap'] = ''
            else:
                row[f'Det{n}_DetType'] = r['det_type']
                row[f'Det{n}_Species'] = _name(r['species'])
                row[f'Det{n}_Conf'] = _fmt(r['conf'])
                row[f'Det{n}_Species2'] = _name(r['species2'])
                row[f'Det{n}_Conf_Species2'] = _fmt(r['conf2'])
                row[f'Det{n}_Gap'] = _fmt(r['gap'])
        else:
            for suff in ['DetType', 'Species', 'Conf', 'Species2', 'Conf_Species2', 'Gap']:
                row[f'Det{n}_{suff}'] = ''

    # ---- Image-level summary --------------------------------------------
    real_labels = [r['species'] for r in recs if is_real_species(r) and not r['suppressed']]
    distinct_real = set(real_labels)
    num_animals = sum(1 for r in recs if r['is_animal'] and not r['suppressed'])
    animal_confs = [r['conf'] for r in recs
                    if r['is_animal'] and r['conf'] is not None and not r['suppressed']]

    row['NumDetections']      = len(detections)
    row['NumAnimals']         = num_animals
    row['HasMultipleSpecies'] = 'true' if len(distinct_real) >= 2 else 'false'
    row['MaxAnimalConf']      = _fmt(max(animal_confs)) if animal_confs else ''
    row['SuppressedFalseDet'] = 'true' if suppressed_any else 'false'
    row['OverflowDetections'] = 'true' if len(detections) > MAX_SLOTS else 'false'

    # ---- Highest-confidence box -> the four SINGLE recognition fields ----
    # Choose the single detection box with the greatest available confidence
    # (classification conf if present, else detection conf). All four fields
    # describe that same box.
    best = None
    best_c = -1.0
    for r in recs:
        if r['suppressed']:
            continue
        c = r['conf'] if r['conf'] is not None else (r['det_conf'] if r['det_conf'] is not None else -1.0)
        if c > best_c:
            best_c = c
            best = r

    if best is not None:
        row['Detection']                = best['det_type']
        row['DetectionConfidence']      = _fmt(best['det_conf'])
        row['Recognitions']             = _name(best['species']) if best['species'] else ''
        row['ClassificationConfidence'] = _fmt(best['conf'])
    else:
        row['Detection'] = row['DetectionConfidence'] = ''
        row['Recognitions'] = row['ClassificationConfidence'] = ''

    # ---- Primary inference (pre-consensus) -------------------------------
    primary = None
    for r in recs_sorted:
        if not r['suppressed']:
            primary = r
            break

    if primary is None:
        inferred_tag, inferred_conf, review = (None, None, 'No')
        primary_species_label = None
        primary_conf_val = None
    elif primary['det_type'] in ('person', 'vehicle') and primary['species'] is None:
        inferred_tag = primary['det_type']
        inferred_conf = conf_rating(primary['det_conf'])
        review = 'No'
        primary_species_label = primary['det_type']
        primary_conf_val = primary['det_conf']
    else:
        sp = primary['species'] if primary['species'] is not None else 'unidentified animal'
        rate = conf_rating(primary['conf'])
        review = _needs_review_base(sp, rate, primary['gap'])
        inferred_tag, inferred_conf = sp, rate
        primary_species_label = sp
        primary_conf_val = primary['conf']

    if len(distinct_real) >= 2:
        review = 'Yes'
    if len(detections) > MAX_SLOTS:
        review = 'Yes'

    # Store raw (lowercase) primary for the consensus pass; final formatting later
    row['_inferred_raw']   = inferred_tag           # lowercase species or None
    row['_inferred_conf']  = inferred_conf
    row['_review']         = review
    row['_primary_conf']   = primary_conf_val
    row['_distinct_real']  = distinct_real

    # Identity + station/deployment
    row['RootFolder']   = ''
    row['File']         = fname
    row['RelativePath'] = rel
    row['DateTime']     = ''                         # filled from EXIF below if found
    row['StationID']    = station
    row['Deployment']   = deployment
    row['_full_path']   = os.path.join(IMAGE_BASE_DIR, *re.split(r'[/\\]+', file_str)) if file_str else ''

    return row


def _needs_review_base(tag, rating, gap):
    if tag is None or tag == SUPPRESSED_LABEL:
        return 'No'
    if tag in DETECTION_ONLY_LABELS or tag == 'false detection':
        return 'No'
    if tag in PRIORITY_REVIEW_SPECIES:
        return 'Yes'
    if tag == 'unidentified animal':
        return 'Yes'
    if rating in ('Low', 'Unresolved'):
        return 'Yes'
    if gap is not None and gap < AMBIGUITY_GAP:
        return 'Yes'
    return 'No'


# ---------------------------------------------------------------------------
# Pass 2 — temporal visit grouping + consensus correction
# ---------------------------------------------------------------------------

def apply_consensus(rows):
    """
    Group rows into visits per camera (StationID+Deployment), sorted by EXIF
    DateTime, split on gaps > VISIT_GAP_SECONDS. Within each visit, correct
    outliers toward a dominant species per the agreed rules.
    Mutates rows in place (sets final InferredTag / InferredConfidence /
    HumanReview).
    """
    # Bucket rows by camera
    by_camera = defaultdict(list)
    for idx, row in enumerate(rows):
        cam = (row['StationID'], row['Deployment'])
        by_camera[cam].append(idx)

    n_overrides = 0
    n_override_review = 0

    for cam, idxs in by_camera.items():
        # Sort by datetime; rows without a datetime go last (can't be clustered)
        dated = [(rows[i].get('_dt'), i) for i in idxs]
        dated_known = sorted([d for d in dated if d[0] is not None], key=lambda x: x[0])
        undated = [i for (dt, i) in dated if dt is None]

        # Build visits from dated rows
        visits = []
        current = []
        prev_dt = None
        for dt, i in dated_known:
            if prev_dt is not None and (dt - prev_dt).total_seconds() > VISIT_GAP_SECONDS:
                visits.append(current)
                current = []
            current.append(i)
            prev_dt = dt
        if current:
            visits.append(current)
        # Undated images each form their own singleton visit (no consensus)
        for i in undated:
            visits.append([i])

        # Process each visit
        for visit in visits:
            if len(visit) < 2:
                continue
            # Tally labelled real-species in the visit
            labels = []
            for i in visit:
                lab = rows[i]['_inferred_raw']
                if lab is not None and lab not in NON_SPECIES:
                    labels.append(lab)
            if not labels:
                continue
            counts = Counter(labels)
            top_species, top_count = counts.most_common(1)[0]
            pct = top_count / len(labels)

            # Mean confidence of the dominant species in this visit
            confs = [rows[i]['_primary_conf'] for i in visit
                     if rows[i]['_inferred_raw'] == top_species
                     and rows[i]['_primary_conf'] is not None]
            mean_conf = sum(confs) / len(confs) if confs else 0.0

            has_consensus = (pct >= CONSENSUS_PCT_MIN and mean_conf >= CONSENSUS_CONF_MIN)
            if not has_consensus:
                continue

            # Correct outliers
            for i in visit:
                row = rows[i]
                cur = row['_inferred_raw']
                if cur == top_species:
                    continue
                # Multi-species images are left to their own review flag
                if len(row['_distinct_real']) >= 2:
                    continue

                outlier_conf = row['_primary_conf']

                # Decide whether this outlier should be overridden
                override = False
                force_review = False

                if cur == 'false detection':
                    # False detection inside a species visit -> assert the animal
                    override = True
                    force_review = True          # option (b)
                elif cur in ('unidentified animal',):
                    override = True
                    force_review = (outlier_conf is not None and outlier_conf >= OUTLIER_OVERRIDE_CONF)
                elif cur in DETECTION_ONLY_LABELS:
                    # person / vehicle are not outliers to override
                    override = False
                elif cur is not None and cur not in NON_SPECIES:
                    # A named species that disagrees with consensus
                    override = True
                    if cur in PRIORITY_REVIEW_SPECIES:
                        force_review = True       # never silently discard priority species
                    elif outlier_conf is not None and outlier_conf >= OUTLIER_OVERRIDE_CONF:
                        force_review = True
                    else:
                        force_review = False

                if override:
                    row['_inferred_raw']  = top_species
                    row['_inferred_conf'] = conf_rating(mean_conf)
                    row['_review'] = 'Yes' if force_review else 'No'
                    n_overrides += 1
                    if force_review:
                        n_override_review += 1

    return n_overrides, n_override_review


# ---------------------------------------------------------------------------
# Finalisation — write the visible columns from the raw fields
# ---------------------------------------------------------------------------

def finalise_rows(rows):
    for row in rows:
        tag = row['_inferred_raw']
        row['InferredTag']        = title_case_tag(tag) if tag else ''
        row['InferredConfidence'] = row['_inferred_conf'] or ''
        row['HumanReview']        = row['_review']

        # Species auto-filled only when no review needed and tag is a real label
        if (row['HumanReview'] == 'No' and tag
                and tag != SUPPRESSED_LABEL):
            row['Species'] = title_case_tag(tag)
        else:
            row['Species'] = ''

        # Blank human-entry columns
        for col in ['Analyst', 'AnalystTag', 'Reviewer1Name', 'Reviewer1Tag',
                    'Reproduction', 'Comments', 'Problem']:
            row[col] = ''
        row['AnimalCount'] = ''
        row['Reference']   = 'false'
        row['PeerReview']  = 'false'

        # Drop internal helper keys
        for k in list(row.keys()):
            if k.startswith('_'):
                del row[k]


# ---------------------------------------------------------------------------
# Column order for the output CSV
# ---------------------------------------------------------------------------

def build_column_order():
    cols = [
        'RootFolder', 'File', 'RelativePath', 'DateTime',
        'StationID', 'Deployment',
        'Detection', 'DetectionConfidence',
        'Recognitions', 'ClassificationConfidence',
        'InferredTag', 'InferredConfidence', 'HumanReview',
        'Species', 'AnimalCount', 'Reproduction',
        'NumDetections', 'NumAnimals', 'HasMultipleSpecies',
        'MaxAnimalConf', 'SuppressedFalseDet', 'OverflowDetections',
    ]
    for n in range(1, MAX_SLOTS + 1):
        cols += [f'Det{n}_DetType', f'Det{n}_Species', f'Det{n}_Conf',
                 f'Det{n}_Species2', f'Det{n}_Conf_Species2', f'Det{n}_Gap']
    cols += ['Analyst', 'AnalystTag', 'Reviewer1Name', 'Reviewer1Tag',
             'Problem', 'Comments', 'Reference', 'PeerReview']
    return cols


def read_template_columns(tdb_path):
    """
    Read the ordered list of (DataLabel, Type) from a Timelapse template (.tdb),
    in SpreadsheetOrder. Returns a list of (name, type) tuples, or None if the
    file can't be read.
    """
    try:
        con = sqlite3.connect(tdb_path)
        cur = con.cursor()
        cur.execute("SELECT DataLabel, Type FROM TemplateTable ORDER BY SpreadsheetOrder")
        cols = [(r[0], r[1]) for r in cur.fetchall()]
        con.close()
        return cols
    except sqlite3.Error as e:
        print(f"  WARNING: could not read template .tdb: {e}")
        return None


def write_import_csv(df_full, tdb_path, import_path):
    """
    Write a Timelapse-import CSV containing only the columns present in the
    template, in the template's order. Any template column the script didn't
    produce is added with a sensible default: Flag fields get 'false' (Timelapse
    rejects blank flags), everything else gets blank. Prints a reconciliation check.
    """
    template_cols = read_template_columns(tdb_path)
    if template_cols is None:
        print("  Import CSV skipped (template unreadable).")
        return

    template_names = [c[0] for c in template_cols]
    produced = set(df_full.columns)
    in_template = set(template_names)

    missing_from_script = [c for c in template_names if c not in produced]
    archive_only = sorted(produced - in_template)

    df_import = pd.DataFrame()
    flag_types = {'flag', 'deleteflag'}   # both need 'false', not blank
    for col, ctype in template_cols:
        if col in df_full.columns:
            df_import[col] = df_full[col]
        elif str(ctype).strip().lower() in flag_types:
            df_import[col] = 'false'     # Timelapse Flag/DeleteFlag must be true/false
        else:
            df_import[col] = ''          # other non-produced columns -> blank

    df_import.to_csv(import_path, index=False)

    print(f"  Import CSV columns: {len(template_names)} (matched to template)")
    if missing_from_script:
        print(f"  Template columns not produced by script (written blank, "
              f"Flags as 'false'): {missing_from_script}")
    if archive_only:
        print(f"  Archive-only columns (kept in full CSV, excluded from import): "
              f"{len(archive_only)} cols incl. {archive_only[:4]}{'...' if len(archive_only) > 4 else ''}")
    print(f"  Saved import CSV: {import_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="JSON-first Timelapse tag inference with temporal consensus.")
    parser.add_argument("input", help="Input recognition .json file")
    parser.add_argument("-o", "--output", help="Output .csv (default in USER SETTINGS)")
    parser.add_argument("--image-base", help="Override IMAGE_BASE_DIR from USER SETTINGS")
    parser.add_argument("--template", help="Override TEMPLATE_TDB_PATH from USER SETTINGS")
    parser.add_argument("--no-exif", action="store_true",
                        help="Skip EXIF reading (disables consensus correction)")
    args = parser.parse_args()

    global IMAGE_BASE_DIR
    if args.image_base:
        IMAGE_BASE_DIR = args.image_base

    tdb_path = args.template if args.template else TEMPLATE_TDB_PATH

    input_path  = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    elif DEFAULT_OUTPUT:
        output_path = Path(DEFAULT_OUTPUT)
    else:
        # No output given and no default set: write next to the input JSON.
        output_path = input_path.with_name(input_path.stem + "_inferred.csv")

    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    if not IMAGE_BASE_DIR:
        print("Note: IMAGE_BASE_DIR is not set (USER SETTINGS) and --image-base")
        print("      was not passed. EXIF timestamps can't be read, so temporal")
        print("      consensus correction will be skipped. Per-image inference")
        print("      still runs. Set --image-base to enable consensus.")

    print(f"Reading category maps from {input_path.name} ...")
    det_map, cls_map = load_category_maps(input_path)
    print(f"  detection_categories:      {len(det_map)} entries")
    print(f"  classification_categories: {len(cls_map)} entries")

    print("Pass 1: streaming images and running per-image inference...")
    rows = []
    n = 0
    with open(input_path, 'rb') as f:
        for image in ijson.items(f, 'images.item'):
            rows.append(process_image(image, det_map, cls_map))
            n += 1
            if n % 25000 == 0:
                print(f"  processed {n:,} images...")
    print(f"  total images: {n:,}")

    # ---- EXIF timestamps --------------------------------------------------
    if args.no_exif:
        print("Skipping EXIF (consensus correction disabled).")
        for row in rows:
            row['_dt'] = None
        n_found = 0
    else:
        print("Reading EXIF timestamps from image files...")
        n_found = 0
        n_missing = 0
        for j, row in enumerate(rows):
            dt = read_exif_datetime(row['_full_path']) if row['_full_path'] else None
            row['_dt'] = dt
            if dt is not None:
                row['DateTime'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                n_found += 1
            else:
                n_missing += 1
            if (j + 1) % 25000 == 0:
                print(f"  read {j+1:,} EXIF timestamps...")
        print(f"  timestamps found: {n_found:,} | missing/unreadable: {n_missing:,}")
        if n_found == 0:
            print("  WARNING: no timestamps were read. Check IMAGE_BASE_DIR in USER")
            print("           SETTINGS points to the folder CONTAINING the station")
            print("           folders (e.g. the parent of 'STATION_01'). Consensus")
            print("           correction will be skipped for images without a time.")

    # ---- Pass 2: consensus correction ------------------------------------
    print("Pass 2: temporal visit grouping + consensus correction...")
    n_over, n_over_rev = apply_consensus(rows)
    print(f"  outliers corrected to consensus: {n_over:,}")
    print(f"    of which flagged for review:   {n_over_rev:,}")

    # ---- Finalise + write -------------------------------------------------
    finalise_rows(rows)
    columns = build_column_order()
    df = pd.DataFrame(rows, columns=columns)

    # 1) Full archive CSV (everything, incl. DetN_* slot columns)
    df.to_csv(output_path, index=False)
    print(f"\nSaved full archive CSV: {output_path}")

    # 2) Timelapse import CSV (template-matched columns only)
    if tdb_path:
        import_path = output_path.with_name(output_path.stem + "_import" + output_path.suffix)
        write_import_csv(df, tdb_path, import_path)
    else:
        print("  No TEMPLATE_TDB_PATH set - import CSV not written.")

    # Summary
    review_yes = (df['HumanReview'] == 'Yes').sum()
    print(f"\nFlagged for human review: {review_yes:,} of {len(df):,}")
    print("\nTop inferred tags:")
    counts = df['InferredTag'].replace('', pd.NA).value_counts(dropna=True).head(15)
    for val, cnt in counts.items():
        print(f"    {str(val):<40} {cnt:>8,}")
    print("\nDone.")


if __name__ == "__main__":
    main()
