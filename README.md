# AutoClaimOpt

> An AI system that teaches itself to review insurance claims — and gets better with every run.

---

## What does it do?

AutoClaimOpt automatically reviews insurance claims to decide whether they should be **accepted** or **rejected** for the reason *"procedure not covered"*.

What makes it special: **it improves its own decision-making over time.** After each batch of reviews, it looks at the claims it got wrong, figures out why, and rewrites its own instructions to do better next time. No human needed.

```
┌─────────────────────────────────────────────────────────────────┐
│                       HOW IT WORKS                              │
│                                                                 │
│   📋 Claims Dataset                                             │
│         │                                                       │
│         ▼                                                       │
│   🤖 AI Reviews Each Claim ──────────────────────────────┐     │
│         │                                                │     │
│         ▼                                                │     │
│   📊 Score Results (F1, Precision, Recall)               │     │
│         │                                                │     │
│         ▼                                                │     │
│   ❌ Find Mistakes (False Positives & Negatives)         │     │
│         │                                                │     │
│         ▼                                                │     │
│   🧠 AI Rewrites Its Own Instructions to Fix Them        │     │
│         │                                                │     │
│         └──────────────── repeat up to 15x ─────────────┘     │
│                                                                 │
│   ✅ Stops when accuracy reaches 90%+ (F1 ≥ 0.90)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## What's inside

```
autoclaimopt/
│
├── optimize.py          ← Run this to start the optimization loop
├── evaluate.py          ← Handles scoring and claim analysis
├── prompt.md            ← The AI's instructions (auto-updated each run)
│
└── data/
    ├── claimDB.json         ← Full dataset (~600 claims with labels)
    └── claimexample.json    ← Quick 3-claim test dataset
```

---

## Before you start

You will need:

| Requirement | Details |
|---|---|
| **Python** | Version 3.11 or higher |
| **Google Cloud account** | With Vertex AI API enabled |
| **`gcloud` CLI** | Installed and authenticated |
| **Project access** | Access to a GCP project with Gemini 2.5 Pro |

---

## Setup — step by step

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd autoclaimopt
```

### 2. Install dependencies

```bash
pip install google-genai
```

Or if you use `uv`:

```bash
uv sync
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

This opens a browser window — just sign in with your Google account that has access to the GCP project.

### 4. Set your project ID

Open `evaluate.py` and update this line near the top:

```python
PROJECT_ID = "your-gcp-project-id"   # ← change this
REGION = "europe-west1"               # ← change if needed
```

### 5. Prepare your claims data

Your claims file must be a JSON array. Each claim needs this shape:

```json
[
  {
    "id": "CLM_001",
    "rejection_reason": "procedure_not_covered",
    "claim_text": "Patient presented with lower back pain...",
    "label": "accepted",
    "supporting_docs": {
      "diagnosis_code": "M54.4",
      "procedure_code": "72148",
      "procedure_description": "MRI lumbar spine without contrast",
      "provider_notes": "Conservative treatment failed after 6 weeks.",
      "policy_type": "COMPREHENSIVE_PLUS",
      "prior_authorization": true
    }
  }
]
```

**`label`** must be either `"accepted"` or `"rejected"` — this is the ground truth the system learns from.

Place your file at `data/claims.json`.

> Want to test with a small dataset first? Use the 3-claim example:
> In `optimize.py`, change `CLAIMS_PATH = "data/claims.json"` to `CLAIMS_PATH = "data/claimexample.json"`

---

## Running it

```bash
python optimize.py
```

That's it. You'll see output like this:

```
AutoClaimOpt — starting optimization loop
Claims: 247 | Max iterations: 15 | F1 target: 0.9

════════════════════════════════════════════════════════════
  Iteration 1 / 15
════════════════════════════════════════════════════════════
  Running evaluation (parallel)...
  [  1/247] CLM_042 predicted=ACCEPTED label=ACCEPTED ✓
  [  2/247] CLM_108 predicted=REJECTED label=ACCEPTED ✗
  ...

  F1=0.7812  Precision=0.8100  Recall=0.7540  Accuracy=0.8300
  TP=186  FP=43  FN=61  TN=214

  ✓ New best F1: 0.7812
  23 misclassified claims — calling meta-agent to improve prompt...
  Prompt updated.

════════════════════════════════════════════════════════════
  Iteration 2 / 15
...
  Target F1 0.9 reached. Done!
```

Results are saved to `results.tsv` after every iteration.

---

## What the scores mean

```
┌──────────────────────────────────────────────────────────┐
│                   SCORING EXPLAINED                       │
│                                                           │
│  F1 Score ────── Overall balance of precision & recall   │
│                  Target: 0.90+  (1.0 = perfect)          │
│                                                           │
│  Precision ───── Of all claims marked REJECTED,          │
│                  how many were actually wrong?            │
│                  High = fewer false alarms                │
│                                                           │
│  Recall ──────── Of all truly invalid claims,            │
│                  how many did we catch?                   │
│                  High = fewer missed rejections           │
│                                                           │
│  TP  True Positives  ── Correctly rejected               │
│  TN  True Negatives  ── Correctly accepted               │
│  FP  False Positives ── Wrongly rejected (false alarm)   │
│  FN  False Negatives ── Missed rejection (slipped through)│
└──────────────────────────────────────────────────────────┘
```

---

## Configuration options

You can tweak these settings at the top of `optimize.py`:

| Setting | Default | What it does |
|---|---|---|
| `MAX_ITERATIONS` | `15` | Maximum number of improvement rounds |
| `F1_THRESHOLD` | `0.90` | Stop early when this accuracy is reached |
| `CLAIMS_PATH` | `data/claims.json` | Path to your labeled claims file |
| `MAX_EXAMPLES_PER_CLASS` | `8` | How many mistakes to show the AI per round |

---

## How the self-improvement works

Each iteration:

```
1. Run all claims through the AI reviewer
      ↓
2. Count correct vs incorrect decisions
      ↓
3. Collect up to 8 false positives + 8 false negatives
      ↓
4. Send them to a "meta-AI" with the message:
   "Here are the claims you got wrong — fix your instructions"
      ↓
5. Save the improved instructions to prompt.md
      ↓
6. If score improved → keep new instructions
   If score got worse → revert to previous version
```

The file `prompt.md` is automatically updated each iteration. You can open it at any time to read the current instructions the AI is using.

---

## Output files

| File | What it contains |
|---|---|
| `prompt.md` | Current (best) AI instructions — updated each run |
| `results.tsv` | Full log of every iteration: F1, precision, recall, confusion matrix |

Open `results.tsv` in Excel or Google Sheets to track improvement over time.

---

## Troubleshooting

**`google.auth.exceptions.DefaultCredentialsError`**
→ Run `gcloud auth application-default login` and try again.

**`Permission denied` on Vertex AI**
→ Make sure your GCP project has the Vertex AI API enabled and your account has the `Vertex AI User` role.

**Optimization stops at a low F1**
→ Your dataset may need more labeled examples, or the claims may have edge cases the AI needs more guidance on. Try increasing `MAX_ITERATIONS`.

**`KeyError: 'id'` or similar JSON errors**
→ Check that every claim in your JSON file has `id`, `claim_text`, `label`, and `supporting_docs` fields.

---

## Tech stack

| Component | Technology |
|---|---|
| AI model | Gemini 2.5 Pro (Google Vertex AI) |
| Language | Python 3.11+ |
| Parallelism | `ThreadPoolExecutor` (3 concurrent calls) |
| Package manager | `uv` or `pip` |
| Output format | TSV log + Markdown prompt |
