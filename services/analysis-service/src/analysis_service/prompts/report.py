REPORT_SYSTEM_PROMPT = """
Summarize analyzed health claims.

Return:
- summary: 2-3 sentences
- overall_rating: accurate | mostly_accurate | mixed

Verdict meaning:
- supported: evidence supports the claim
- unsupported_by_evidence: evidence does not support the claim
- no_evidence_found: no relevant publications found in this run (uncertainty, not contradiction)

Rating rules:
- no_evidence_found is less severe than unsupported_by_evidence
- accurate: mostly supported, no clear unsupported pattern
- mostly_accurate: generally supported, with some unsupported_by_evidence or no_evidence_found
- mixed: substantial mix of supported and unsupported_by_evidence/no_evidence_found

Output ONLY valid JSON with keys "summary" and "overall_rating".
No markdown, code fences, or extra text.

Input from user is a JSON array of claim objects.
Use only the provided items.
"""

REPORT_USER_PROMPT = """{claims}"""
