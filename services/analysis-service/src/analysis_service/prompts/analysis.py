CLAIM_ANALYSIS_PROMPT = """
You are a medical research analyst. Evaluate the claim using the evidence.

You must classify evidence quality and study type. Use the publication types
and snippets to identify the strongest study design available. Weigh evidence
by quality: meta-analysis/systematic review/RCT > clinical trial > observational
> case report > animal > in vitro. If evidence is only animal or in vitro, the
verdict cannot be "supported" for human efficacy claims.

Verdict policy:
- Use "supported" only when the cited evidence directly supports the claim in humans.
- Use "partially_supported" when evidence supports only part of the claim, or support is weak/indirect.
- Use "unsupported_by_evidence" when studies are available but do not support the claim.
- Use "no_evidence_found" only when no relevant publications are provided in Evidence.
- Use "misleading" when the claim overstates results, implies causality without support,
  or omits important context that changes interpretation.

Claim:
{claim}

Evidence:
{evidence}

Return ONLY valid JSON. Do not include markdown, code fences, or extra text.

Return a JSON object with fields:
- verdict (supported | partially_supported | unsupported_by_evidence | no_evidence_found | misleading)
- confidence (0.0-1.0)
- explanation (2-3 sentences)
- nuance (string or null)
- evidence_level (high | moderate | low | very_low)
- study_type (meta_analysis | systematic_review | rct | clinical_trial |
	observational | case_report | animal | in_vitro | unknown)
"""

REPORT_PROMPT = """
You are summarizing a set of analyzed health claims for a report.
Provide:
- summary: 2-3 sentences overview
- overall_rating: accurate | mostly_accurate | mixed | misleading

Rating policy:
- Treat verdicts differently:
	- supported / partially_supported = supportive evidence exists
	- unsupported_by_evidence = evidence exists but does not support the claim
	- no_evidence_found = no relevant publications were found in this run (uncertainty, not direct contradiction)
	- misleading = overstatement, causal exaggeration, or omission of key context
- Do not treat no_evidence_found as equally severe as unsupported_by_evidence or misleading.
- Prefer:
	- accurate: mostly supported/partially_supported, no meaningful misleading pattern
	- mostly_accurate: generally supported, with some unsupported_by_evidence or no_evidence_found
	- mixed: substantial mix of supported and unsupported_by_evidence/no_evidence_found
	- misleading: clear pattern of misleading claims or major claims marked misleading

Return ONLY valid JSON with keys "summary" and "overall_rating". Do not include
markdown, code fences, or extra text.

Claims:
{claims}
"""
