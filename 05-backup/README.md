# Back up

> ⚠️ **Work in progress — test before relying on it.** This is example code shared to illustrate the workflow. This particular version has not yet been tested on a real image set, and it **overwrites image files in place**. Before running it on data you care about, copy a small sample of images to a separate folder and test on that copy first — confirm the tags are written correctly and that nothing is lost. Use `--dry-run` to preview, and `--keep-originals` to retain backups.

This stage writes the verified species identifications from [Timelapse](https://saul.cpsc.ucalgary.ca/timelapse/) back into the image files' own metadata, so the identification travels with the image — useful for archiving, sharing, or re-importing later.

Note: Timelapse itself does have this function - however, last time I used it, it wrote metadata to the image in a way that you then couldn't see the species tags, or search for them, by using Finder/Explorer (like you can when you export tags to metadata in a program like digiKam). However, they will be there and you can use ExifTool to check. But if you'd prefer the tags be written to the metadata like digiKam, the code below will do this. 

**Input:** Timelapse export (`.csv` or `.xlsx`) &nbsp;·&nbsp; **Output:** the same images, with the `Species` value written into their `Keywords` and `Subject` metadata

## What the script does

[`write_metadata.py`](write_metadata.py) reads a Timelapse export, builds each image's full path from its `RelativePath` + `File` columns, and writes the `Species` value into the image's **Keywords** and **Subject** metadata fields using [exiftool](https://exiftool.org). All edits for a run are sent to exiftool in a single batch, so tagging large image sets is fast.

It skips rows with a blank species or a missing image file (reporting how many), and offers a `--dry-run` so you can preview before changing anything.

## Before you run it

You need **exiftool** installed and on your PATH — it is a separate tool, not a Python package. Check with `exiftool -ver`.

- **Mac:** `brew install exiftool` (install [Homebrew](https://brew.sh) first if needed).
- **Windows:** download the Windows executable from [exiftool.org](https://exiftool.org), unzip it, rename `exiftool(-k).exe` to `exiftool.exe`, and place it somewhere on your PATH (or in the same folder you run the script from).

The Python packages (`pandas`, and `openpyxl` for `.xlsx` input) install automatically on first run if missing.

You also need to tell the script where your images live — the folder that **contains** your station/deployment folders — either by editing `IMAGE_BASE_DIR` in the `USER SETTINGS` block or passing `--image-base`.

## Usage

```bash
# preview first (recommended) — changes nothing:
python write_metadata.py timelapse_export.csv \
    --image-base "/path/to/folder/containing/the/images" --dry-run

# then write the tags:
python write_metadata.py timelapse_export.csv \
    --image-base "/path/to/folder/containing/the/images"
```

The input may be `.csv` or `.xlsx` — the script detects which from the file extension. On Windows, use `python` instead of `python3`, `^` instead of `\` for line continuation, and Windows-style paths in quotes.

### Overwriting and backups

By default the script **overwrites the original image files in place** (the tag is written into the existing file). This is usually what you want for this step, but it does change your files. To keep a safety copy, pass `--keep-originals` and exiftool will leave a `<name>_original` backup beside each changed image.

## Notes

- Both `Keywords` and `Subject` are written by default. To change which fields are used, edit `METADATA_FIELDS` in the `USER SETTINGS` block.
- If your export uses different column headers, adjust the `COL_*` names in `USER SETTINGS`.
- This is a worked example — check it does what you expect on a small copied sample before running it across a whole project.

---

*Code licensed under Apache 2.0; this documentation under CC BY 4.0. See the repository [`LICENSE-NOTE.md`](../LICENSE-NOTE.md).*
