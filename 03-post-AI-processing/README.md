# Post-AI processing

This stage takes the `.json` output from [AddaxAI](https://addaxdatascience.com/addaxai/) / and prepares it for human review in [Timelapse](https://saul.cpsc.ucalgary.ca/timelapse/).

**Input:** recognition `.json` &nbsp;·&nbsp; **Output:** a full archive `.csv` plus a Timelapse-ready `_import.csv`

## What the script does

[`postprocess_recognitions.py`](postprocess_recognitions.py) reads a MegaDetector-format recognition JSON (streamed, so multi-gigabyte files are fine) and writes one CSV row per image. In brief, it:

- picks the highest-confidence detection box per image and fills four summary fields (detection type and confidence, top species and classification confidence), while keeping the full per-detection breakdown as archive columns;
- reads each image's timestamp from its EXIF metadata, so the temporal logic runs **before** Timelapse is opened;
- groups images into temporal "visits" per camera (station + deployment) and applies **consensus correction** — where one species clearly dominates a visit, disagreeing outliers are relabelled, with low-confidence ones corrected silently and higher-confidence or priority-species disagreements flagged for human review;
- auto-flags low-confidence, ambiguous, unidentified, multi-species, and priority-species images for review; and
- writes two CSVs: a full archive (every column) and an `_import` version containing only the columns in your Timelapse template, in the template's order.

## Before you run it

This is a worked example from one project. **The species lists, label groupings, and thresholds in the script are examples** tied to one south-eastern Australian study area — open the `USER SETTINGS` block near the top and edit them for your own fauna before relying on the output. In particular, replace `PRIORITY_REVIEW_SPECIES` and `LABEL_REMAP`.

You also need to tell the script where things are. The three settings can be set in the `USER SETTINGS` block or passed on the command line:

| What | Setting | Command-line flag |
|------|---------|-------------------|
| Folder containing your station folders | `IMAGE_BASE_DIR` | `--image-base` |
| Your Timelapse template | `TEMPLATE_TDB_PATH` | `--template` |
| Output CSV (optional) | `DEFAULT_OUTPUT` | `-o` |

If the output path is left blank, the CSV is written next to the input JSON. If the image base is left blank, per-image inference still runs but EXIF-based consensus correction is skipped.

## Requirements

- **Python 3.8 or newer.**
- The packages `ijson`, `pandas`, and `Pillow`. The script installs these automatically on first run if they're missing, so you usually don't need to do anything. To install them yourself instead, run `pip install ijson pandas Pillow`.

To check whether Python is installed, open a terminal (see below) and run `python3 --version` on Mac, or `python --version` on Windows. If you don't have it, download it from [python.org](https://www.python.org/downloads/). On Windows, tick **"Add Python to PATH"** in the installer.

## How to run it

First, open a command line and move into the folder that contains the script.

### On a Mac

1. Open **Terminal** (press `Cmd + Space`, type *Terminal*, press Enter).
2. Move into this folder. The easiest way: type `cd ` (with a space), then drag the `03-postprocess` folder from Finder onto the Terminal window and press Enter.
3. Run the script:

```bash
python3 postprocess_recognitions.py recognitions.json \
    --image-base "/path/to/folder/containing/station/folders" \
    --template   "/path/to/your_template.tdb" \
    -o           "output.csv"
```

The `\` at the end of each line lets you continue one command across several lines. You can also type it all on a single line without the `\`.

### On a Windows PC

1. Open **Command Prompt** (press the Start key, type *cmd*, press Enter).
2. Move into this folder. The easiest way: open the `03-postprocess` folder in File Explorer, click the address bar, type `cmd`, and press Enter — Command Prompt opens already pointing at that folder.
3. Run the script (note the `^` line-continuation character on Windows, and `python` rather than `python3`):

```bat
python postprocess_recognitions.py recognitions.json ^
    --image-base "C:\path\to\folder\containing\station\folders" ^
    --template   "C:\path\to\your_template.tdb" ^
    -o           "output.csv"
```

You can also type it all on a single line without the `^`.

### Notes for both

- Put **quotes around any path that contains spaces**, as shown above.
- Replace `recognitions.json` with the path to your own JSON file (or just its name, if it's in this same folder).
- The script expects images organised on disk as `STATION/DEPLOYMENT/IMAGE.JPG`, and a recognition JSON in MegaDetector output format.
- To run without the consensus step (for a quick test, or if your images aren't to hand), add `--no-exif`.

## A note on Timelapse FixedChoice fields

The `_import.csv` is matched to your template's columns, so Timelapse won't reject it on structure. One thing to check: if your template has a `FixedChoice` field for `Species`, every species value the script can emit must already exist in that field's choice list (in the same spelling and capitalisation) or Timelapse may blank it on import. Make sure your template's `Species` choices cover the labels your model produces.

---

*Code licensed under Apache 2.0; this documentation under CC BY 4.0. See the repository [`LICENSE-NOTE.md`](../LICENSE-NOTE.md).*
