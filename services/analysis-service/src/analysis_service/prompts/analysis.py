CLAIM_ANALYSIS_PROMPT = """
You are a medical research analyst. Evaluate the claim using the evidence.

You must classify evidence quality and study type. Use the publication types
and snippets to identify the strongest study design available. Weigh evidence
by quality: meta-analysis/systematic review/RCT > clinical trial > observational
> case report > animal > in vitro. If evidence is only animal or in vitro, the
verdict cannot be "supported" for human efficacy claims.

Claim:
{claim}

Evidence:
{evidence}

Return ONLY valid JSON. Do not include markdown, code fences, or extra text.

Return a JSON object with fields:
- verdict (supported | partially_supported | unsupported | misleading)
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

Return ONLY valid JSON with keys "summary" and "overall_rating". Do not include
markdown, code fences, or extra text.

Claims:
{claims}
"""
