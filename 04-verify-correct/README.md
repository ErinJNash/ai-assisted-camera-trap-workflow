# Verify & correct

This stage takes the `_import.csv` from the [post-AI processing step](../03-postprocess/) into [Timelapse](https://saul.cpsc.ucalgary.ca/timelapse/) for human review, where an analyst checks and corrects the AI tags, or manually tagged those images the AI has not labelled.  

**Input:** `_import.csv` (from stage 3) &nbsp;·&nbsp; **Output:** `.xlsx` with AI recognitions alongside analyst and reviewer tags

## The Timelapse template

A Timelapse template (`.tdb`) defines the data fields used during review. You can download the one I use here:

**[`timelapse-template.tdb`](timelapse-template.tdb)** — download, then open it in Timelapse to start a new image set.

This template includes fields for the AI outputs carried over from stage 3 (detection, recognitions, inferred tag, confidences), plus fields for the human review workflow — an analyst tag, a reviewer tag, and a final species tag — so AI and human labels sit side by side rather than overwriting each other.

> **Note on species choices:** the `Species`, `Analyst tag`, and `Reviewer 1 tag` fields use a fixed list of species. If you adapt this template, make sure every label your model can output exists in that list (in the same spelling and capitalisation), or Timelapse will blank it on import.

## Coming soon

I'm preparing fuller documentation for this stage, including:

- general instructions on how I use Timelapse to verify and correct AI tags, and
- notes on the review workflow — how AI recognitions, analyst tags, and reviewer tags relate to one another, and how I programmatically check and flag discrepancies. 

In the meantime, the best starting points are the official [Timelapse Image Analyser](https://timelapse.ucalgary.ca/) site and Saul Greenberg's guides, which cover installation and the recognitions workflow in detail.

---

*Documentation licensed under CC BY 4.0; the template under CC BY 4.0. See the repository [`LICENSE-NOTE.md`](../LICENSE-NOTE.md).*
