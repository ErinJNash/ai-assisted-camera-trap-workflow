# AI-Assisted Camera Trap Workflow

*An example end-to-end workflow for turning camera trap images into ecological data, and a practitioner's guide to deciding whether, and how, to use AI along the way.*

---

> ## ⭐ Start here — before you grab any code
>
> The workflow below links out to the code, documents, and files for each stage. But **which tools you use — and whether to use AI at all — is a decision, not a default.** Before picking up code from any stage, please read [**Deciding whether (and how) to use AI**](#deciding-whether-and-how-to-use-ai-in-camera-trap-workflows) further down this page. It is the most important thing here. The short version: every option, including all-human review, has an error profile; your job is to understand the error profile of each tool as it relates to your particular image set, and to choose an error profile you can live with for *your* end goals.

---

## The workflow at a glance

This camera trap workflow runs in six stages. Each links to the relevant folder in this repository.

| Stage | What happens | In / out | Go to |
|------:|--------------|----------|-------|
| **1. Organise images** | Rename and organise image files by folder path into a fixed structure with unique names | images → organised images | [`01-capture-retrieve/`](01-capture-retrieve/) |
| **2. AI processing** | Run detection + classification models over images. I use [AddaxAI](https://addaxdatascience.com/addaxai/) for this step. Document settings used. | images → `.json` | [`02-addaxai/`](02-addaxai/) |
| **3. Post AI processing** | Python script: consensus clustering to fix likely errors, flag species for human review, reshape for import into Timelapse | `.json` → `.csv` | [`03-postprocess/`](03-postprocess/) |
| **4. Verify & correct** | Human review in [Timelapse](https://timelapse.ucalgary.ca/) (example template provided). AI tags sit alongside human primary analyst and reviewer tags | `.csv` → `.xlsx` | [`04-verify-correct/`](04-verify-correct/) |
| **5. Back up** | Python script writes the verified tags into image metadata | `.xlsx` → tagged images | [`05-backup/`](05-backup/) |
| **6. Summarise for further analysis** | Summarise basic information e.g. detections; example R code that reads the Timelapse `.xlsx` (fuller pipeline kept in a private repo) | `.xlsx` → summaries | [`06-summarise/`](06-summarise/) |

---

<!-- ============================================================= -->
<!-- THE AI GUIDE                                                  -->
<!-- ============================================================= -->

# Deciding whether (and how) to use AI in camera trap workflows

*A guide for practictioners about choosing, evaluating, and responsibly deploying AI in ecological image analysis.*

## Contents

- [1. Introduction and scope](#1-introduction-and-scope)
  - [AI in biodiversity conservation](#ai-in-biodiversity-conservation)
- [2. Foundations: the kinds of AI you will meet](#2-foundations-the-kinds-of-ai-you-will-meet)
  - [Analytical AI versus generative AI](#analytical-ai-versus-generative-ai)
  - [Detectors and classifiers, and how they work together](#detectors-and-classifiers-and-how-they-work-together)
- [3. How these models err](#3-how-these-models-err)
  - [Detector errors](#detector-errors)
  - [Classifier errors](#classifier-errors)
  - [Why this distinction matters](#why-this-distinction-matters)
- [4. A framework for choosing](#4-a-framework-for-choosing)
  - [Start with your values](#start-with-your-values)
  - [Then weigh the consequences of error](#then-weigh-the-consequences-of-error)
  - [Then compare the real options](#then-compare-the-real-options)
- [5. Evaluating a model on your own data](#5-evaluating-a-model-on-your-own-data)
  - [Build a validation set](#build-a-validation-set)
  - [Compute metrics that mean something](#compute-metrics-that-mean-something)
  - [Confidence thresholds: your main lever](#confidence-thresholds-your-main-lever)
  - [Class imbalance and rare species](#class-imbalance-and-rare-species)
- [6. Workflows, including "no AI"](#6-workflows-including-no-ai)
  - [No AI](#no-ai)
  - [Human-in-the-loop triage](#human-in-the-loop-triage)
  - [Specific workflow options](#specific-workflow-options)
- [7. Practical considerations](#7-practical-considerations)
  - [Data management and reproducibility](#data-management-and-reproducibility)
  - [Privacy and legal considerations](#privacy-and-legal-considerations)
  - [Cost, compute, and accessibility](#cost-compute-and-accessibility)
- [8. Key messages and the road ahead](#8-key-messages-and-the-road-ahead)
- [9. Glossary and further reading](#9-glossary-and-further-reading)
  - [Glossary](#glossary)
  - [Further reading](#further-reading)

---

## 1. Introduction and scope

This is a working document about how I think through the use of AI models in camera trap workflows for ecological monitoring. It is not a tutorial for any single piece of software, and it is not a claim that AI is always the right answer (because it's not!). It is an attempt to set out the reasoning I use to decide whether and how to use AI on a given project — and to share what I have learned.

This guide is aimed at ecologists, conservation practitioners, and anyone wrangling large volumes of camera trap imagery who is trying to decide whether a detector, a classifier, or no model at all is the right tool for their particular purpose.

One framing point before we start. It is tempting to treat AI as inherently risky and human review as the safe default. That framing is misleading. Every option has an error profile, including the use of humans and especially the use of humans under particular circumstances. The question we need to ask is not "Is AI risky?" but "Which of the options open to me have error profiles I can live with, given what I am trying to do and what my values are?"

### AI in biodiversity conservation

Using AI for ecological image analysis is not new, but it has become dramatically more accessible. Tools that once required a machine-learning team and a GPU cluster now run on a laptop with a friendly interface, and what were once expensive proprietary products are increasingly being released open-source, for others to use for free and further develop. That accessibility is a big win for conservation.

But it also carries risks. The rest of this document is about managing those risks deliberately.

## 2. Foundations: kinds of AI

### Analytical AI versus generative AI

Most of the AI used in camera trap work is what we can loosely call **analytical** AI: models trained to make predications and draw conclusions about an existing image, such as "there is an animal in this image" or "this is an image of a Southern Brown Bandicoot." MegaDetector and species classifiers (including those used in iNaturalist) fall into this category. These models are small, and especially when they run on your local computer rather than in the cloud, aren't associated with the notorious water and energy use issues associated with AI.

Analytical AI is distinct from **generative** AI, which produces *new content* (text, images). For example, if we gave one of the generative AI services (Claude, ChatGPT, Co-Pilot, Gemini, etc.) two camera trap images — one of a Common Brush-tailed Possum and the other an Eastern Ring-tailed Possum — and asked it to combine them to form a new species, a "Ring-brushed-tailed possum," that would be generative AI. Generative AI is associated with significant resource use.

In this document, when I say "AI" I mean analytical AI. The distinction matters mainly because they make mistakes in different ways, and conflating them leads to bad intuitions about reliability.

### Detectors and classifiers, and how they work together

A **detector** answers a spatial question: is there something of interest in this image, and if so, where within the image is it? MegaDetector, for example, is an open-source model originally made by the 'Microsoft AI for Good Lab' that can tell if a camera trap image has a person, vehicle or animal in it, or whether it is "empty." It draws a box around the animal/person/vehicle within the image without saying what species the animal is. It also assigns a confidence score to its detection, e.g. 0.9 means MegaDetector is 90% confident there is an animal in the image.

A **classifier** answers an identity question: what animal is within the box within the image? Classifiers assign a label (e.g. "Southern Brown Bandicoot") and a confidence score (e.g. 0.85).

In a typical pipeline these two types of models are used in sequence: the detector finds and crops the animal, and the classifier identifies what is in the crop. This division of labour matters because it localises where errors come from. A missed animal is a detector problem; a misidentified one is a classifier problem; and the two can compound — a classifier never gets the chance to identify an animal the detector failed to find.

## 3. How these models err

You cannot choose responsibly between options until you understand how each one breaks.

### Detector errors

- **False positives:** the detector reports an animal in the image when there is in fact no animal in the image. MegaDetector sometimes thinks that grasstrees, sticks or tree trunks with interesting markings that look like eyes are animals.

- **False negatives:** the detector misses an animal that is actually present in the image. MegaDetector 5a and 5b wasn't very good at detecting Australian reptiles, for example. For our camera sites in the Otway Ranges and Otway Plains of Victoria, I've found that when MegaDetector misses animals, it's often when they're moving away from the camera, like the Short-beaked Echina below. Although more recent releases of MegaDetector (such as Redwood) perform better on Australian animals than previous versions, MegaDetector is trained on a range of animals from across the world, not exclusively Australian animals.

False negatives are the more concerning of the two types of error, because a missed detection is invisible which a false positive at least announces itself for review.

<table>
<tr>
<td><img src="docs/images/ExampleFalsePositiveStickDeer.jpg" width="350" alt="A camera trap image in which a curved stick lying on leaf litter has been boxed by MegaDetector and labelled 'fallow deer .63' by the classifier."><br><em>False positive: a fallen stick boxed by MegaDetector and labelled "fallow deer" with 0.63 confidence.</em></td>
<td><img src="docs/images/FalseNegativeEchidna.jpg" width="350" alt="A camera trap image of forest leaf litter with an echidna that was not detected."><br><em>False negative: an echidna (left of frame) is missed by MegaDetector.</em></td>
</tr>
</table>

### Classifier errors

Classifier errors come in two flavours that are worth keeping separate. The first is a **strictly false** classification: the label is simply wrong, as when an image of a Wedge-tailed Eagle is labelled as a Laughing Kookaburra.

The second is better thought of as an **inaccuracy rate** across a unit of analysis. Camera trap data is rarely one image at a time; it comes in sequences and episodes. If one image in a sequence of five is strictly false, or ten images in an episode of 250 are strictly false, the consequences depend entirely on how you aggregate. A single wrong frame may be irrelevant if you only care whether a species was present in the episode, and decisive if you are counting frames. The same underlying error can be trivial or fatal depending on your unit of analysis.

### Why this distinction matters

Holding these error types apart lets you ask the right question of any workflow: not "How accurate is it?" but "What kinds of mistakes does it make, how often, and where do they land relative to what I care about?"

## 4. A framework for choosing

Choosing a workflow is not primarily a technical decision; it is a decision about which errors you are willing to tolerate, made in light of what you are trying to achieve.

### Start with your values

Two broad kinds of values are relevant to your decision. **Epistemic** values concern getting at the truth — accuracy, completeness, reproducibility. **Non-epistemic** values concern everything else that legitimately matters when using camera traps and their data for research and monitoring — time, cost, animal welfare, the stakes of research/monitoring finding or a management decision, obligations to funders or communities. It's important to be clear about what your values are and how weighty different values are in relation to other values for your particular project and circumstances. This may be your decision to make; or it might be a decision that a research group or governance body has to make collectively.

### Weigh the consequences of error

When our conclusions can be wrong and being wrong has consequences for what we value, the choice of how much evidence to demand — and which errors to risk — is not itself value-free. Translated to camera traps: deciding to accept a workflow with a particular error rate/risk profile is a value judgement about the costs of those errors, and benefits of what you gain by accepting that risk profile; it's not a neutral technical setting. (Philosophers of science like Heather Douglas and Kevin Elliott are worth reading directly if this idea is new; see [Further reading](#further-reading).)

### Then compare the real options

Only now does it make sense to compare options, and the comparison must be concrete. The question is never "Is this model good?" in the abstract. It is:

- *how does **this model** perform on **your dataset**, for **your species of interest**; and*
- *what is the **comparative performance of the alternatives**?* — using no AI (i.e. using humans, or using particular humans), using a different AI model, using a particular AI model with a particular workflow that has a higher degree of "human in the loop" checks and balances, etc.

## 5. Evaluating a model on your own data

This is the practical core. You cannot know how a model performs for you until you measure it on labelled data from your own project.

### Build a validation set

Collate a set of images you have labelled manually and that you are very confident have been labelled accurately that are similar to the images you intend to analyse with AI (camera make/model, camera set up, habitat type, species mix, etc.). Make sure this set includes your species of interest, your hardest conditions (night, rain, partial views), and your rare classes. A validation set that contains only easy daytime images will mislead you. These images should not have been used to train the model. 

### Compute metrics that mean something

- **Precision:** of the things the model flagged as "X", what fraction really were "X"? (Low precision = many false alarms.)
- **Recall:** of the things that really were "X", what fraction did the model find? (Low recall = many misses.)
- **Per-class performance:** overall accuracy hides the truth. Look at each species separately — especially the rare ones.
- **Confusion matrix:** which classes get mistaken for which? This tells you exactly where the dangerous confusions live.

These metrics can not only inform a decision to use or not use AI, but can also be used to select particular AI workflows, set AI processing settings (see 'confidence thresholds' next) and design post-processing steps to correct common errors or flag certain species for human review (see '03_postprocess'). 

### Class imbalance and rare species

In some cases, the species you care most about may be the one the model has seen least or perhaps not at all. Rare classes are where errors cluster, and where a single confident misclassification can distort an entire analysis. Evaluate rare species specifically; do not let a high overall accuracy reassure you about a class the model has barely encountered.

## 6. Workflows, including "no AI"

With your values, error tolerances, and measured performance in hand, you are in a position to choose a workflow.

### No AI

For some purposes, the right answer will be to not use AI at all. For example, for some research purposes, the error rates associated with the AI models currently available to assist in processing camera trap images may be too high for researchers to tolerate for a particular purpose. In this case, they may opt for a completely manual, human-driven workflow.

This is a legitimate, defensible outcome of this process. Going through the above process should help you to understand:

- The error rates associated with using humans, including particular groups of humans, to process and annotate the data compared to AI-assisted workflows.
- The consequences of human-based errors and the impacts of these errors on end-values.
- The benefits of using a fully human workflow, and what values are being traded off to support this.

### Human-in-the-loop triage

The most useful middle ground is usually to let AI triage rather than decide. Use the model to sort, then spend human attention where it matters. Saul Greenberg's has an excellent guide to using a spectrum of different AI assisted workflows in Timelapse ([Timelapse Image Recognition Guide](https://timelapse.ucalgary.ca/wp-content/uploads/Guides/TimelapseImageRecognitionGuide.pdf)). 

### AI with programmatic post-processing 

As you learn more about how the particular AI model you use with your datasets performs, you will get a better understanding of the common errors it makes and you can design further code to programmatically correct these errors (See: 03-postprocess for example Python code i currently use).

Note that Addax AI is likely to soon release an updated version of the Addax AI platform that has similar features built in, so this code may soon not be needed. 

## 7. Practical considerations

### AddaxAI settings
- Different configurations trade speed, recall, and effort differently; choose the setting that matches the error profile you decided on, not the default. (My settings are documented in [`02-addaxai/`](02-addaxai/).)


### Data management and reproducibility

- Keep AI outputs separate from human verifications, so you can always tell which is which.
- Record the model name, version, and confidence threshold that produced each set of labels. "Classified by AI" is not reproducible; "Classified by model X v2.1 at threshold 0.7" is.
- Version your outputs. Re-running a newer model is an improvement only if you can compare it against what came before.

### Privacy and legal considerations

Camera traps capture people as well as animals. Have a plan for human captures — how they are stored, who can see them, and when they are deleted — and check the obligations that apply in your jurisdiction and on the land you are working on.

### Cost, compute, and accessibility

Accessibility has improved, but barriers remain: hardware, processing time, and the learning curve of new software all have real costs. Factor them in honestly when comparing AI against human-only workflows, rather than treating model inference as free.

## 8. Key messages and the road ahead

**AI is a tool, not a replacement for human judgement.** It changes where human attention is spent; it does not remove the need for it.

**Any tool can be used well or badly.** How well partly depends on the skill of the user — and that skill can be built, by understanding how these models work and where they fail.

**Tools will improve, but not on their own.** Progress turns on camera technology, on the composition of training libraries, and on the quality and accuracy of the annotations in those libraries. Better data, not just bigger models, is what moves the field.

## 9. Glossary and further reading

### Glossary

- **Detector** — a model that locates objects of interest in an image (e.g. MegaDetector).
- **Classifier** — a model that assigns an identity label to an image or crop.
- **Precision** — fraction of positive predictions that are correct.
- **Recall** — fraction of true cases that the model correctly finds.
- **Confidence threshold** — the score above which a model's output is accepted; the main lever for trading precision against recall.
- **Episode / sequence** — a group of images treated as a unit of analysis; the choice of unit shapes how errors matter.
- **Epistemic / non-epistemic values** — values about reaching the truth versus values about other legitimate goals (time, cost, welfare, stakes).

### Further reading

- Heather Douglas, on the role of values and the consequences of error in scientific inference.
- Kevin Elliott, on values in science and tolerable inductive risk.
- MegaDetector and the broader open-source camera trap AI ecosystem documentation.
- Timelapse Image Analyser and its recognitions guide ([saul.cpsc.ucalgary.ca/timelapse](https://saul.cpsc.ucalgary.ca/timelapse/)).

---

## Licence

This repository is dual-licensed: **code** under the [Apache License 2.0](LICENSE), and all **written and visual material** (guides, README prose, the workflow diagram, and the Timelapse template) under [Creative Commons Attribution 4.0 (CC BY 4.0)](LICENSE-docs.txt). See [`LICENSE-NOTE.md`](LICENSE-NOTE.md) for details and suggested attribution.

---

<sub>↑ Back to [the workflow at a glance](#the-workflow-at-a-glance)</sub>
