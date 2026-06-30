###############################################################################
## SUMMARISE DETECTIONS FROM A TIMELAPSE EXPORT (WORKSHEET)
## -------------------------------------------------------------------------
## Reads a Timelapse export (.csv or .xlsx), applies an independence interval
## and a per-station deployment cut-off, and writes summary tables of
## detections per station, deployment and species.
##
## This is a worked EXAMPLE from one camera trap workflow. Edit the USER
## SETTINGS block below before running it on your own data.
##
## Companion script: summarise_from_metadata.R reads species tags from image
## EXIF metadata instead of from the Timelapse export.
###############################################################################

## ---------------------------------------------------------------------------
## STEP 0 — Packages (installs them only if they are not already present)
## ---------------------------------------------------------------------------
required_packages <- c("dplyr", "stringr", "lubridate", "readr", "readxl", "writexl")
to_install <- required_packages[!(required_packages %in% installed.packages()[, "Package"])]
if (length(to_install) > 0) install.packages(to_install)

library(dplyr)
library(stringr)
library(lubridate)
library(readr)
library(readxl)
library(writexl)

###############################################################################
## >>> USER SETTINGS — EDIT THESE BEFORE RUNNING <<<
###############################################################################

# The Timelapse export to summarise (.csv or .xlsx). The script auto-detects
# the type from the file extension.
#   >>> SET THIS to your tagged-data export <<<
input_path <- ""

# Folder where the output tables are written.
#   >>> SET THIS <<<
output_dir <- ""

# Deployment summary workbook (.xlsx) giving the per-station 28-day cut-off
# time. See the README for the exact format this file must have. Leave "" to
# skip the deployment cut-off step entirely (Steps 1, 2 and 4 still run).
#   >>> SET THIS, or leave "" to skip the cut-off <<<
deployment_summary_path <- ""

# --- Deployment summary layout (only used if deployment_summary_path is set) -
# The sheet name, and the columns holding the station and the cut-off time.
deployment_sheet        <- "CamAppSummary"
deployment_station_col  <- "Station"
deployment_cutoff_col   <- "28 day mark"

# Timezone the timestamps are in (xlsx has no timezone; applied on parsing).
#   >>> CHANGE if your study area is not in this timezone <<<
timezone <- "Australia/Victoria"

# Independence interval, in minutes (same species + station + deployment).
independence_minutes <- 5

# Column names in your export. Change these if your headers differ. The script
# renames `file_col` -> FileName and `station_col` -> Station internally.
datetime_col <- "DateTime"
file_col     <- "File"
station_col  <- "StationID"
species_col  <- "Species"
deployment_col <- "Deployment"   # set to NA if your data has no Deployment column

# Species/label values to exclude from the summaries.
excluded_species <- c("", "Unknown", "Empty", "False Detection",
                      "Person", "Vehicle", "Start_Stop")

###############################################################################
## >>> END USER SETTINGS <<<
###############################################################################

if (input_path == "" || output_dir == "") {
  stop("Please set input_path and output_dir in the USER SETTINGS block.")
}
if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

## Helper: POSIXct -> character before writing (xlsx has no timezone support,
## so we format to local-time strings to avoid silent UTC shifts).
format_datetimes <- function(df) {
  df %>% mutate(across(where(is.POSIXct), ~ format(.x, "%Y-%m-%d %H:%M:%S")))
}

## ---------------------------------------------------------------------------
## STEP 1 — Load the export (auto-detects .csv or .xlsx) and build record table
## ---------------------------------------------------------------------------
file_ext <- tolower(tools::file_ext(input_path))
if (file_ext == "csv") {
  raw_data <- read_csv(input_path, col_types = cols(.default = col_character()),
                       show_col_types = FALSE)
} else if (file_ext %in% c("xlsx", "xlsm")) {
  raw_data <- read_xlsx(input_path, col_types = "text")
} else {
  stop("Unsupported file type: ", file_ext, ". Please provide a .csv or .xlsx file.")
}

# Rename the configured columns to internal standard names
rec.db.full <- raw_data %>%
  rename(FileName = !!file_col, Station = !!station_col) %>%
  mutate(
    DateTimeOriginal = as.POSIXct(str_trim(.data[[datetime_col]]),
                                  format = "%Y-%m-%d %H:%M:%S", tz = timezone)
  )

# Group keys depend on whether a Deployment column is present
has_deployment <- !is.na(deployment_col) && deployment_col %in% names(raw_data)
group_keys <- if (has_deployment) c("Station", "Deployment", "Species") else c("Station", "Species")

rec.db.full <- rec.db.full %>%
  arrange(across(all_of(if (has_deployment) c("Station", "Deployment", "DateTimeOriginal")
                        else c("Station", "DateTimeOriginal"))))

write_xlsx(format_datetimes(rec.db.full),
           file.path(output_dir, "FullRecordTable_AllImagesArchive.xlsx"))

## ---------------------------------------------------------------------------
## STEP 2 — Independence rule (same species/station[/deployment] within interval)
## ---------------------------------------------------------------------------
rec.db.species5 <- rec.db.full %>%
  filter(!is.na(Species), !(Species %in% excluded_species)) %>%
  arrange(across(all_of(c(group_keys[group_keys != "Species"], "Species", "DateTimeOriginal")))) %>%
  group_by(across(all_of(group_keys))) %>%
  mutate(
    time_diff = as.numeric(difftime(DateTimeOriginal, lag(DateTimeOriginal), units = "mins")),
    keep = is.na(time_diff) | time_diff > independence_minutes
  ) %>%
  filter(keep) %>%
  select(-time_diff, -keep) %>%
  ungroup()

write_xlsx(format_datetimes(rec.db.species5),
           file.path(output_dir, "SpeciesDetectionsAll_IndependentDetections.xlsx"))

## ---------------------------------------------------------------------------
## STEP 3 — Apply per-station deployment cut-off (optional)
## ---------------------------------------------------------------------------
if (deployment_summary_path != "") {
  deployment_cutoffs <- read_xlsx(deployment_summary_path, sheet = deployment_sheet) %>%
    transmute(
      Station = as.character(.data[[deployment_station_col]]),
      cut_off_28days = as.POSIXct(
        format(.data[[deployment_cutoff_col]], "%Y-%m-%d %H:%M:%S"),
        format = "%Y-%m-%d %H:%M:%S", tz = timezone)
    ) %>%
    filter(!is.na(Station), !is.na(cut_off_28days))

  # Hard error if any station in the data lacks a cut-off
  missing_cutoffs <- setdiff(unique(rec.db.species5$Station), unique(deployment_cutoffs$Station))
  if (length(missing_cutoffs) > 0) {
    stop("Station(s) in the data are missing from the deployment summary; add ",
         "them and rerun: ", paste(missing_cutoffs, collapse = ", "), call. = FALSE)
  }
  extra_cutoffs <- setdiff(unique(deployment_cutoffs$Station), unique(rec.db.species5$Station))
  if (length(extra_cutoffs) > 0) {
    message("Note: station(s) in the deployment summary have no records in the data: ",
            paste(extra_cutoffs, collapse = ", "))
  }

  rec.db.final <- rec.db.species5 %>%
    left_join(deployment_cutoffs, by = "Station") %>%
    filter(DateTimeOriginal <= cut_off_28days) %>%
    ungroup()
} else {
  message("No deployment summary set — skipping the deployment cut-off step.")
  rec.db.final <- rec.db.species5
}

## ---------------------------------------------------------------------------
## STEP 4 — Summary of detections
## ---------------------------------------------------------------------------
summary_counts <- rec.db.final %>%
  count(across(all_of(group_keys)), name = "Detections") %>%
  arrange(across(all_of(group_keys)))

write_xlsx(summary_counts,
           file.path(output_dir, "Summary_Station_Species_Detections.xlsx"))

message("Done. Summary tables written to: ", output_dir)
