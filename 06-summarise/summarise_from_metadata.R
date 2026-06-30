###############################################################################
## SUMMARISE DETECTIONS FROM IMAGE METADATA
## -------------------------------------------------------------------------
## Reads species tags written into image EXIF metadata (e.g. by the stage 5
## "back up" step), applies an independence interval and a deployment cut-off,
## and writes summary tables of detections per station and species.
##
## This is a worked EXAMPLE from one camera trap workflow. Edit the USER
## SETTINGS block below before running it on your own data.
##
## Companion script: summarise_from_worksheet.R reads the Timelapse export
## (.csv / .xlsx) directly instead of reading image metadata.
###############################################################################

## ---------------------------------------------------------------------------
## STEP 0 — Packages (installs them only if they are not already present)
## ---------------------------------------------------------------------------
required_packages <- c("exifr", "dplyr", "stringr", "lubridate")
to_install <- required_packages[!(required_packages %in% installed.packages()[, "Package"])]
if (length(to_install) > 0) install.packages(to_install)

library(exifr)
library(dplyr)
library(stringr)
library(lubridate)

###############################################################################
## >>> USER SETTINGS — EDIT THESE BEFORE RUNNING <<<
###############################################################################

# Folder containing your images (searched recursively). Each image's tags are
# read from its own EXIF metadata.
#   >>> SET THIS to your image folder <<<
image_dir <- ""

# Where the output CSV tables are written.
#   >>> SET THIS to where you want the summary tables saved <<<
output_dir <- ""

# Timezone your cameras' timestamps are in. EXIF timestamps carry no timezone,
# so this is applied when parsing them. See OlsonNames() for valid values.
#   >>> CHANGE if your study area is not in this timezone <<<
timezone <- "Australia/Victoria"

# Independence interval, in minutes. Consecutive records of the SAME species at
# the SAME station within this interval count as one independent detection.
independence_minutes <- 5

# Deployment length, in days. Records after (first image + this many days) at a
# station are excluded, to standardise survey effort.
# NOTE: this script derives the cut-off from each station's FIRST image. If you
# have true deployment dates, the companion worksheet script can use them.
deployment_days <- 28

# Species/label values to exclude from the summaries (non-animal or non-target
# tags). Edit to match the labels in YOUR data.
excluded_species <- c("", "Start_Stop", "Empty", "Unknown",
                      "False Detection", "Person", "Vehicle")

###############################################################################
## >>> END USER SETTINGS <<<
###############################################################################

if (image_dir == "" || output_dir == "") {
  stop("Please set image_dir and output_dir in the USER SETTINGS block.")
}
if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

## ---------------------------------------------------------------------------
## STEP 1 — Read EXIF metadata from all images
## ---------------------------------------------------------------------------
files <- list.files(
  image_dir,
  pattern   = "\\.(jpg|jpeg|png|tif|tiff)$",
  full.names = TRUE,
  recursive = TRUE,
  ignore.case = TRUE
)
message("Found ", length(files), " image files in ", image_dir)
if (length(files) == 0) stop("No images found. Check image_dir.")

meta <- read_exif(
  files,
  tags = c("FileName", "Directory", "DateTimeOriginal", "Species")
)

# OPTIONAL inspection — uncomment if you want to check how tags were written:
# str(meta$Species)
# head(meta$Species, 100)

## ---------------------------------------------------------------------------
## STEP 2 — Build a full record table of all images
## ---------------------------------------------------------------------------
rec.db.full <- meta %>%
  mutate(
    Station = basename(Directory),   # last folder name = station
    Species = as.character(Species),
    DateTimeOriginal = as.POSIXct(
      DateTimeOriginal,
      format = "%Y:%m:%d %H:%M:%S",
      tz     = timezone
    )
  ) %>%
  arrange(Station, DateTimeOriginal)

# Flatten any list columns so they can be written to CSV
rec.db.full <- rec.db.full %>%
  mutate(across(where(is.list), ~ sapply(., paste, collapse = "|")))

write.csv(
  rec.db.full,
  file.path(output_dir, "FullRecordTable_AllImagesArchive.csv"),
  row.names = FALSE
)
print(table(rec.db.full$Species, useNA = "ifany"))

## ---------------------------------------------------------------------------
## STEP 3 — Per-station deployment cut-off (first image + deployment_days)
## ---------------------------------------------------------------------------
deployment_cutoffs <- rec.db.full %>%
  group_by(Station) %>%
  summarise(
    first_image_time = min(DateTimeOriginal, na.rm = TRUE),
    last_image_time  = max(DateTimeOriginal, na.rm = TRUE),
    deployment_duration_days = as.numeric(
      difftime(last_image_time, first_image_time, units = "days")),
    cut_off = first_image_time + as.difftime(deployment_days, units = "days"),
    deviation_from_protocol_days = round(deployment_duration_days - deployment_days, 1),
    .groups = "drop"
  ) %>%
  arrange(Station)

write.csv(
  deployment_cutoffs,
  file.path(output_dir, "DeploymentDurationSummary_byStation.csv"),
  row.names = FALSE
)

## ---------------------------------------------------------------------------
## STEP 4 — Independence rule (same species, same station, within interval)
## ---------------------------------------------------------------------------
rec.db.species_indep <- rec.db.full %>%
  filter(!is.na(Species), !(Species %in% excluded_species)) %>%
  arrange(Station, Species, DateTimeOriginal) %>%
  group_by(Station, Species) %>%
  mutate(
    time_diff = as.numeric(difftime(DateTimeOriginal, lag(DateTimeOriginal), units = "mins")),
    keep = is.na(time_diff) | time_diff > independence_minutes
  ) %>%
  filter(keep) %>%
  select(-time_diff, -keep) %>%
  ungroup() %>%
  arrange(Station, DateTimeOriginal)

write.csv(
  rec.db.species_indep,
  file.path(output_dir, "SpeciesTable_IndependentDetections.csv"),
  row.names = FALSE
)

## ---------------------------------------------------------------------------
## STEP 5 — Apply the deployment cut-off AFTER the independence rule
## ---------------------------------------------------------------------------
rec.db.species_indep_cut <- rec.db.species_indep %>%
  left_join(deployment_cutoffs %>% select(Station, cut_off), by = "Station") %>%
  filter(DateTimeOriginal <= cut_off) %>%
  arrange(Station, DateTimeOriginal)

write.csv(
  rec.db.species_indep_cut,
  file.path(output_dir, "SpeciesTable_IndependentDetections_withinDeployment.csv"),
  row.names = FALSE
)

## ---------------------------------------------------------------------------
## STEP 6 — Summary: detections per station and species
## ---------------------------------------------------------------------------
summary_counts <- rec.db.species_indep_cut %>%
  count(Station, Species, name = "Detections") %>%
  arrange(Station, Species)

write.csv(
  summary_counts,
  file.path(output_dir, "Summary_Station_Species_Detections.csv"),
  row.names = FALSE
)

message("Done. Summary tables written to: ", output_dir)
