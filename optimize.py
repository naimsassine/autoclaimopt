"""
optimize.py — Main optimization loop.

Iteratively improves prompt.md against the labeled claims dataset.
Stop conditions: F1 >= F1_THRESHOLD or iterations >= MAX_ITERATIONS.
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from evaluate import call_gemini, compute_metrics, evaluate, load_claims

# ── Configuration ─────────────────────────────────────────────────────────────

MAX_ITERATIONS = 15
F1_THRESHOLD = 0.90
CLAIMS_PATH = "data/claims.json"
PROMPT_PATH = "prompt.md"
RESULTS_PATH = "results.tsv"

# How many misclassified examples to send to the meta-agent per class
MAX_EXAMPLES_PER_CLASS = 8

# ── Helpers ───────────────────────────────────────────────────────────────────


def load_prompt() -> str:
    return Path(PROMPT_PATH).read_text()


def save_prompt(prompt: str) -> None:
    Path(PROMPT_PATH).write_text(prompt)


def log_result(iteration: int, metrics: dict, note: str = "") -> None:
    path = Path(RESULTS_PATH)
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        if write_header:
            writer.writerow(
                [
                    "timestamp",
                    "iteration",
                    "f1",
                    "precision",
                    "recall",
                    "accuracy",
                    "tp",
                    "fp",
                    "fn",
                    "tn",
                    "note",
                ]
            )
        writer.writerow(
            [
                datetime.now().isoformat(),
                iteration,
                metrics["f1"],
                metrics["precision"],
                metrics["recall"],
                metrics["accuracy"],
                metrics["tp"],
                metrics["fp"],
                metrics["fn"],
                metrics["tn"],
                note,
            ]
        )


def build_meta_prompt(
    current_prompt: str,
    metrics: dict,
    results: list[dict],
    claims_by_id: dict,
) -> str:
    """Build the prompt sent to the meta-agent (prompt optimizer)."""
    fp_results = [
        r for r in results if r["predicted"] == "REJECTED" and r["label"] == "ACCEPTED"
    ]
    fn_results = [
        r for r in results if r["predicted"] == "ACCEPTED" and r["label"] == "REJECTED"
    ]

    def format_examples(examples: list[dict], label: str) -> str:
        out = ""
        for r in examples[:MAX_EXAMPLES_PER_CLASS]:
            claim = claims_by_id.get(r["id"], {})
            out += f"""
--- {label} | ID: {r["id"]} ---
Claim text: {claim.get("claim_text", "N/A")}
Supporting docs: {json.dumps(claim.get("supporting_docs", {}), indent=2)}
Agent reasoning: {r["reasoning"][:600]}
Agent confidence: {r["confidence"]}
"""
        return out

    fp_section = format_examples(fp_results, "FALSE POSITIVE (predicted REJECTED, truly ACCEPTED)")
    fn_section = format_examples(fn_results, "FALSE NEGATIVE (predicted ACCEPTED, truly REJECTED)")

    return f"""You are an expert prompt engineer specializing in insurance claim analysis.
Your task is to improve the prompt below to reduce misclassifications.

## Current Metrics
- F1:        {metrics["f1"]:.4f}  (target: ≥ 0.90)
- Precision: {metrics["precision"]:.4f}  (false positive rate: {metrics["fp"]}/{metrics["fp"] + metrics["tp"] or 1})
- Recall:    {metrics["recall"]:.4f}  (false negative rate: {metrics["fn"]}/{metrics["fn"] + metrics["tp"] or 1})
- Accuracy:  {metrics["accuracy"]:.4f}
- TP: {metrics["tp"]} | FP: {metrics["fp"]} | FN: {metrics["fn"]} | TN: {metrics["tn"]}

## Misclassified Claims

### False Positives — {len(fp_results)} claims wrongly REJECTED
{fp_section if fp_results else "None"}

### False Negatives — {len(fn_results)} claims wrongly ACCEPTED
{fn_section if fn_results else "None"}

## Current Prompt
{current_prompt}

## Instructions
1. Diagnose what's causing the false positives and false negatives above.
2. Rewrite the prompt to fix these patterns without overfitting to specific claim IDs.
3. You may update the chain-of-thought steps, clarify rejection criteria, or add/replace few-shot examples.
4. Preserve the JSON response format exactly: {{reasoning, decision, confidence}}.
5. Preserve the {{claim_text}} and {{supporting_docs}} placeholders.
6. Add a comment block at the very top: <!-- CHANGES: <brief explanation of what you changed and why> -->

Return ONLY the complete improved prompt. No explanations outside the comment block.
"""


def strip_code_fence(text: str) -> str:
    """Remove markdown code fences that the model may wrap output in."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")].strip()
    return text


# ── Main Loop ─────────────────────────────────────────────────────────────────


def main() -> None:
    claims = load_claims(CLAIMS_PATH)
    claims_by_id = {c["id"]: c for c in claims}

    best_f1 = -1.0
    best_prompt = load_prompt()

    print(f"AutoClaimOpt — starting optimization loop")
    print(f"Claims: {len(claims)} | Max iterations: {MAX_ITERATIONS} | F1 target: {F1_THRESHOLD}")
    print(f"Prompt: {PROMPT_PATH} | Results log: {RESULTS_PATH}")

    for iteration in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'═' * 60}")
        print(f"  Iteration {iteration} / {MAX_ITERATIONS}")
        print(f"{'═' * 60}")

        current_prompt = load_prompt()

        print("  Running evaluation (parallel)...")
        eval_out = evaluate(claims, current_prompt, max_workers=3, verbose=True)
        metrics = eval_out["metrics"]
        results = eval_out["results"]

        print(
            f"\n  F1={metrics['f1']:.4f}  "
            f"Precision={metrics['precision']:.4f}  "
            f"Recall={metrics['recall']:.4f}  "
            f"Accuracy={metrics['accuracy']:.4f}"
        )
        print(
            f"  TP={metrics['tp']}  FP={metrics['fp']}  "
            f"FN={metrics['fn']}  TN={metrics['tn']}"
        )

        improved = metrics["f1"] > best_f1
        if improved:
            best_f1 = metrics["f1"]
            best_prompt = current_prompt
            note = "improved"
            print(f"  ✓ New best F1: {best_f1:.4f}")
        else:
            note = "no_improvement — reverting"
            print(f"  ✗ No improvement (best={best_f1:.4f}) — reverting prompt")
            save_prompt(best_prompt)

        log_result(iteration, metrics, note)

        # Stop conditions
        if metrics["f1"] >= F1_THRESHOLD:
            print(f"\n  Target F1 {F1_THRESHOLD} reached. Done!")
            break

        if iteration == MAX_ITERATIONS:
            print(f"\n  Reached max iterations ({MAX_ITERATIONS}). Stopping.")
            break

        # Generate improved prompt
        misclassified = [r for r in results if r["predicted"] != r["label"]]
        print(
            f"\n  {len(misclassified)} misclassified claims — "
            "calling meta-agent to improve prompt..."
        )

        meta_prompt = build_meta_prompt(current_prompt, metrics, results, claims_by_id)
        raw_improved = call_gemini(meta_prompt, temperature=0.4)
        improved_prompt = strip_code_fence(raw_improved)

        if "{claim_text}" not in improved_prompt or "{supporting_docs}" not in improved_prompt:
            print("  ⚠ Meta-agent dropped required placeholders — skipping this update")
            save_prompt(best_prompt)
        else:
            save_prompt(improved_prompt)
            print("  Prompt updated.")

    print(f"\n{'═' * 60}")
    print(f"  Optimization complete. Best F1: {best_f1:.4f}")
    print(f"  Best prompt saved to {PROMPT_PATH}")
    print(f"  Results log: {RESULTS_PATH}")
    save_prompt(best_prompt)


if __name__ == "__main__":
    main()
