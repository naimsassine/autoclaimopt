"""
evaluate.py — Immutable. Do not edit during a run.

Loads claims, runs the claim analyzer agent in parallel, computes metrics.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from google import genai

PROJECT_ID = "qover-ai-agent-test"
REGION = "europe-west1"
MODEL_NAME = "gemini-2.5-pro"


def get_client() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)


def call_gemini(prompt: str, temperature: float = 0.0) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt],
        config={
            "temperature": temperature,
        },
    )
    return response.text


def load_claims(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def build_claim_prompt(claim: dict, prompt_template: str) -> str:
    prompt = prompt_template.replace("{claim_text}", claim.get("claim_text", ""))
    prompt = prompt.replace(
        "{supporting_docs}",
        json.dumps(claim.get("supporting_docs", {}), indent=2),
    )
    return prompt


def parse_decision(raw: str) -> tuple[str, str, str]:
    """Extract decision, reasoning, confidence from raw model output."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

    try:
        data = json.loads(cleaned)
        decision = data.get("decision", "").upper().strip()
        reasoning = data.get("reasoning", "")
        confidence = data.get("confidence", "UNKNOWN").upper()
    except (json.JSONDecodeError, AttributeError):
        # Fallback: scan text for REJECTED / ACCEPTED
        upper = raw.upper()
        if "REJECTED" in upper and "ACCEPTED" not in upper:
            decision = "REJECTED"
        elif "ACCEPTED" in upper and "REJECTED" not in upper:
            decision = "ACCEPTED"
        else:
            # Ambiguous — default to ACCEPTED (conservative)
            decision = "ACCEPTED"
        reasoning = raw
        confidence = "LOW"

    if decision not in ("ACCEPTED", "REJECTED"):
        decision = "ACCEPTED"

    return decision, reasoning, confidence


def analyze_claim(claim: dict, prompt_template: str) -> dict:
    """Run the claim analyzer on a single claim. Returns prediction + metadata."""
    prompt = build_claim_prompt(claim, prompt_template)
    try:
        raw = call_gemini(prompt, temperature=0.0)
    except Exception as e:
        raw = f"ERROR: {e}"

    decision, reasoning, confidence = parse_decision(raw)

    return {
        "id": claim["id"],
        "predicted": decision,
        "label": claim["label"].upper(),
        "reasoning": reasoning,
        "confidence": confidence,
        "raw": raw,
    }


def evaluate(
    claims: list[dict],
    prompt_template: str,
    max_workers: int = 3,
    verbose: bool = False,
) -> dict:
    """Run analyzer on all claims in parallel. Returns metrics + per-claim results."""
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_claim = {
            executor.submit(analyze_claim, claim, prompt_template): claim
            for claim in claims
        }
        for i, future in enumerate(as_completed(future_to_claim), 1):
            result = future.result()
            results.append(result)
            if verbose:
                match = "✓" if result["predicted"] == result["label"] else "✗"
                print(
                    f"  [{i:3d}/{len(claims)}] {result['id']} "
                    f"predicted={result['predicted']} label={result['label']} {match}"
                )

    metrics = compute_metrics(results)
    return {"results": results, "metrics": metrics}


def compute_metrics(results: list[dict]) -> dict:
    tp = sum(
        1 for r in results if r["predicted"] == "REJECTED" and r["label"] == "REJECTED"
    )
    fp = sum(
        1 for r in results if r["predicted"] == "REJECTED" and r["label"] == "ACCEPTED"
    )
    fn = sum(
        1 for r in results if r["predicted"] == "ACCEPTED" and r["label"] == "REJECTED"
    )
    tn = sum(
        1 for r in results if r["predicted"] == "ACCEPTED" and r["label"] == "ACCEPTED"
    )

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    accuracy = (tp + tn) / len(results) if results else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "total": len(results),
    }
