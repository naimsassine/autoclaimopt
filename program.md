# AutoClaimOpt — Optimization Loop Instructions

## Overview
You are an autonomous prompt optimization agent. Your goal is to improve `prompt.md` so that the insurance claim analyzer achieves the highest possible F1 score on the evaluation set.

## The Loop
Run `optimize.py`. It will:
1. Load `data/claims.json` and `prompt.md`
2. Run the claim analyzer on all claims in parallel
3. Compute precision, recall, and F1
4. If F1 >= 0.90 or iterations >= 15: stop
5. Call you (the meta-agent) with misclassified examples to improve the prompt
6. Log results to `results.tsv` and iterate

## Your Job (as Meta-Agent)
When called with a set of misclassified claims and current metrics, you must:
1. **Diagnose the error pattern** — are false positives clustering around a specific claim type? Are false negatives missing a key rejection signal?
2. **Propose targeted fixes** — adjust chain-of-thought instructions, update few-shot examples, clarify ambiguous criteria
3. **Preserve structure** — keep the JSON response format and chain-of-thought format intact
4. **Don't overfit** — do not add rules that only apply to 1-2 specific claims; generalize
5. **Annotate your changes** — always include a `<!-- CHANGES: ... -->` comment block at the top of the new prompt explaining what you changed and why

## Constraints
- Only edit `prompt.md`
- Never touch `evaluate.py` or `data/claims.json`
- Keep the prompt focused on the single rejection reason defined in the `<!-- REJECTION REASON: ... -->` header
- Prefer surgical edits over complete rewrites unless the current prompt is clearly broken
- If precision is low (too many false positives): tighten the rejection criteria, add more "ACCEPTED" examples
- If recall is low (too many false negatives): broaden the rejection signals, add more "REJECTED" examples

## Metric Target
F1 >= 0.90 (balancing precision and recall equally). If you must trade one for the other, prefer recall (catching true rejections) over precision.

## Results Log
Each iteration writes a row to `results.tsv`:
`timestamp | iteration | f1 | precision | recall | accuracy | tp | fp | fn | tn | note`
