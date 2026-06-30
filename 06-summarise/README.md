# Summarise for analysis

> ⚠️ **Example code — test on a small sample first.** These scripts are shared to illustrate the workflow. Run each on a small copy of your data and check the outputs before relying on them. They have not been tested in this exact form on a full dataset.

This stage takes the verified detections and summarises them into per-station, per-species detection tables ready for further analysis (occupancy, activity, abundance, and so on). It applies two common standardising steps: an **independence interval** (so a single animal lingering in front of a camera is counted once, not many times) and a **deployment cut-off** (so every station contributes a comparable survey effort).

There are two scripts, depending on where your verified species tags live:

| Script | Reads from | Use when |
|--------|-----------|----------|
| [`summarise_from_metadata.R`](summarise_from_metadata.R) | species tags in the **image EXIF metadata** | you ran the [stage 5 back-up step](../05-backup/) and the tags are written into the images |
| [`summarise_from_worksheet.R`](summarise_from_worksheet.R) | the **Timelapse export** (`.csv` / `.xlsx`) | you want to summarise straight from the exported table |

Both produce the same kind of output: a full record archive, an independent-detections table, and a final summary count of detections per station and species.

## Requirements

- **R** (and ideally RStudio). Download from [r-project.org](https://www.r-project.org/).
- The scripts install any missing R packages themselves on first run (`dplyr`, `stringr`, `lubridate`, plus `exifr` for the metadata script, or `readr`/`readxl`/`writexl` for the worksheet script).
- For `summarise_from_metadata.R` you also need **exiftool** installed (the `exifr` package calls it). See [exiftool.org](https://exiftool.org).

## How to run

Open the script in RStudio, edit the **USER SETTINGS** block at the top (file paths, timezone, and the ecological parameters described below), then run the whole script. Or from a terminal:

```bash
Rscript summarise_from_metadata.R
# or
Rscript summarise_from_worksheet.R
```

Each script stops with a clear message if the required paths in USER SETTINGS are still blank.

## Settings you will want to check

Both scripts expose the key parameters at the top rather than burying them:

- **`timezone`** — camera timestamps carry no timezone, so this is applied when parsing them. The default is `Australia/Victoria`; change it for your region (see `OlsonNames()` in R for valid values).
- **`independence_minutes`** — consecutive records of the same species at the same station within this interval count as one detection. Default is 5 minutes; some studies use 30 or 60.
- **`deployment_days`** (metadata script) — the survey length used for the cut-off, derived from each station's first image. Default 28.
- **`excluded_species`** — the labels treated as non-target (empties, people, vehicles, etc.). Edit to match the labels in your data.

## The deployment summary (worksheet script only)

`summarise_from_worksheet.R` can apply a per-station deployment cut-off read from a separate workbook, which is more accurate than deriving it from the first image. If you use this, set `deployment_summary_path` and make sure the workbook has:

- a sheet named in `deployment_sheet` (default `CamAppSummary`),
- a column named in `deployment_station_col` (default `Station`) whose values match the station names in your data, and
- a column named in `deployment_cutoff_col` (default `28 day mark`) giving the cut-off date/time per station.

If any station in your data is missing from this summary, the script stops with an error listing them — nothing downstream is written until they are added. Leave `deployment_summary_path` blank to skip the cut-off step entirely.

## A note on the method

The two scripts group the independence rule slightly differently: the worksheet script can include `Deployment` in the grouping (station + deployment + species), while the metadata script groups by station + species. The core approach — apply the independence rule first, then the deployment cut-off, then count — is the same. The ecological choices (independence interval, deployment length, which species to exclude) are yours to set; the defaults here are examples, not recommendations.

---

*Code licensed under Apache 2.0; this documentation under CC BY 4.0. See the repository [`LICENSE-NOTE.md`](../LICENSE-NOTE.md).*
