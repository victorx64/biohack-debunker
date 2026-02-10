CLAIM_ANALYSIS_PROMPT = """
You are a medical research analyst. Evaluate the claim using the evidence.

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
