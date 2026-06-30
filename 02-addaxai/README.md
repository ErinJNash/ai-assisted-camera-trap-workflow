# AI processing

This stage covers how I run camera trap images through [AddaxAI](https://addaxdatascience.com/addaxai/) to detect and classify animals, and the settings I use.

## Coming soon

I'm preparing documentation for this stage that will include:

- the AddaxAI settings I use (including confidence thresholds), and
- notes on how those settings feed into the post-processing stage that follows.

## Confidence thresholds: your main lever

The confidence threshold is the single most actionable control most users have, and it is where the framework for balancing errors and values becomes concrete. Raising the threshold accepts fewer detections: precision goes up, recall goes down — you make fewer false alarms but miss more. Lowering it does the reverse.

There is no universally correct threshold. The right one falls directly out of your consequences-of-error analysis. If missing even one image of a threatened species is unacceptable for your end-purposes, you favour recall and accept more false positives to review. If a missed image or even sequence of common species does not matter for your purposes, you favour precision. Set the threshold deliberately, record it, and revisit it per species rather than accepting a single global default.
