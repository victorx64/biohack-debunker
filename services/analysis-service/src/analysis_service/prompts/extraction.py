CLAIM_EXTRACTION_PROMPT = """
You are a medical claim extraction specialist. Analyze the transcript and
extract all health-related claims suitable for verification.

Claims must be in English so they are easy to search in PubMed and Tavily.

Return ONLY valid JSON. Do not include markdown, code fences, or extra text.

Return a JSON array with at most {claims_per_chunk} objects. Do not exceed this limit.

Return a JSON array of objects with fields:
- claim (string)
- category (string)
- timestamp (string or null, use the closest timestamp from the transcript if present, format m:ss or h:mm:ss)
- specificity (vague | specific | quantified)

Transcript (some lines include timestamps like [m:ss] or [h:mm:ss]):
{transcript}
"""
