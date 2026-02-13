CLAIM_EXTRACTION_PROMPT = """
You are a medical claim extraction specialist. Analyze the transcript and
extract all health-related claims suitable for verification.

Return ONLY valid JSON. Do not include markdown, code fences, or extra text.
Ensure all double quotes inside string values are escaped (\").

Return a JSON object with a top-level "claims" array. Do not return a bare array.
The "claims" array must contain at most {claims_per_chunk} objects. Do not exceed this limit.
If more valid claims are present than the limit allows, keep only the most extraordinary claims first (surprising, counterintuitive, highly specific, or high-impact health assertions), then fill remaining slots with the next most verification-worthy claims.

Each object in "claims" has fields:
- claim (string)
- timestamp (string or null, use the closest timestamp from the transcript if present, format m:ss or h:mm:ss)
- specificity (vague | specific | quantified)
- search_query (string, a PubMed search query based on the claim, following the rules below)

Rules for claim text:
- Each claim must be atomic: exactly one verifiable health assertion per claim.
- Split compound statements connected by "and", "or", commas, or semicolons into separate claims when they contain different assertions.
- Keep claim text short and literal (prefer 6-16 words; max 20 words).
- Preserve original meaning; do not add hedging or extra details not present in transcript.
- Keep medically relevant qualifiers only when essential (population, dose, timeframe, outcome).

Rules for search_query:
- Prioritize recall (finding enough relevant papers) over overly narrow precision.
- Use 1-3 core concepts from the claim; do not force weak/generic concepts if they over-restrict results.
- Use English terms only; if the claim is in another language, translate key terms to standard English medical terminology.
- Put [tiab] after each term or quoted phrase.
- For each core concept, include 2-5 close synonyms/variants and join them with OR inside parentheses.
- Use AND only between indispensable concepts.
- Avoid generic constraint terms unless central to the claim (e.g., "time", "effect", "level", "change", "result").
- For prevalence/frequency claims, include epidemiology wording when relevant (e.g., prevalence, frequency, proportion, rate, "experience sampling").
- Always wrap OR groups in parentheses before combining with AND.
- The search_query value must be a single-line valid JSON string.
- To avoid JSON breakage, do NOT use double quotes inside search_query.
- For multi-word concepts, use grouped word conjunction instead of phrase quotes, e.g. (mind[tiab] AND wandering[tiab]) instead of "mind wandering"[tiab].
- Avoid extra words like "study" or "research".
- Example: (omega-3[tiab] OR "fish oil"[tiab]) AND triglycerides[tiab]
- Example (JSON-safe broad behavioral neuroscience claim): (((mind[tiab] AND wandering[tiab]) OR (task-unrelated[tiab] AND thought[tiab]) OR (stimulus-independent[tiab] AND thought[tiab]) OR (spontaneous[tiab] AND cognition[tiab]) OR daydreaming[tiab]) AND (prevalence[tiab] OR frequency[tiab] OR proportion[tiab] OR rate[tiab] OR (experience[tiab] AND sampling[tiab])))

Valid response example (structure only):
{{"claims":[{{"claim":"...","timestamp":"1:23","specificity":"specific","search_query":"..."}}]}}

Transcript (some lines include timestamps like [m:ss] or [h:mm:ss]):
{transcript}
"""
