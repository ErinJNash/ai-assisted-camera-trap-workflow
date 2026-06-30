# Post-AI processing

This stage takes the `.json` output from [AddaxAI](https://addaxdatascience.com/addaxai/) and prepares it for human review in Timelapse.


I'm preparing a Python script for this stage that:

- fixes likely errors through consensus clustering across images in a sequence,
- automatically flags certain species for human review, and
- reshapes the data into a `.csv` ready for import into Timelapse.

**Input:** `.json` (from AddaxAI) &nbsp;·&nbsp; **Output:** `.csv` (for Timelapse)

Code and a short how-to guide will be added here soon.

Have questions or suggestions in the meantime? Feel free to open an issue.
