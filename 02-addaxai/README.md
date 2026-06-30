# addaxai

<!-- TODO: describe this stage, how to run its code/use its files, inputs and outputs. -->
Confidence thresholds: your main lever

The confidence threshold is the single most actionable control most users have, and it is where the framework for balancing errors and values becomes concrete. Raising the threshold accepts fewer detections: precision goes up, recall goes down — you make fewer false alarms but miss more. Lowering it does the reverse.

There is no universally correct threshold. The right one falls directly out of your consequences-of-error analysis. If missing even one image of a threatened species is unacceptable for your end-purposes, you favour recall and accept more false positives to review. If a missed image or even sequence of common species does not matter for your purposes, you favour precision. Set the threshold deliberately, record it, and revisit it per species rather than accepting a single global default.
