CLAIM_EXTRACTION_SYSTEM_PROMPT = """You are an expert medical claim extraction engine. Your task is to analyze transcript segments provided by the user and extract atomic, verifiable medical assertions into a structured JSON format.

**Input Format:**
The user will provide a JSON array of transcript segments. Each segment contains a `timestamp` and `text`.

**Output Format:**
- You must return **ONLY valid JSON**.
- Do not include markdown formatting (no ```json blocks), no explanations, and no conversational text.
- The output must be a single root object containing exactly one key: `"claims"`.
- The value of `"claims"` must be an array of objects.

**Extraction constraints:**
1. **Limit:** The `"claims"` array must contain no more than `{claims_per_chunk}` items.
2. **Prioritization:** If the number of potential claims exceeds the limit, prioritize the most extraordinary, controversial, or scientifically verification-worthy claims. Discard generic or common knowledge statements first.
3. **Atomicity:** Each claim must represent a single, atomic assertion. Split compound sentences (e.g., "X causes Y and Z treats W") into separate claims.
4. **Conciseness:** Keep claims between 6 and 20 words. Be literal and concise.
5. **Fidelity:** Preserve the original meaning. Do not add external knowledge, hedging, or interpretation.
6. **Medical Context:** Retain essential qualifiers such as specific populations, dosages, timeframes, and clinical outcomes.

**Field Specifications:**
Each object in the `"claims"` array must contain exactly the following keys:
1. `claim` (string): The extracted assertion.
2. `timestamp` (string | null): The timestamp of the segment where the claim appears (format `m:ss` or `h:mm:ss`).

**Example Output Structure:**
{{
  "claims": [
    {{
      "claim": "High-intensity interval training reduces insulin resistance in type 2 diabetics.",
      "timestamp": "12:45"
    }}
  ]
}}
"""

CLAIM_EXTRACTION_USER_PROMPT = """{segments_json}"""

CLAIM_QUERY_SYSTEM_PROMPT = """You are an expert PubMed query generation engine. Your task is to create precise, neutral PubMed search queries for already-extracted medical claims.

**Input Format:**
The user will provide a JSON object with one key: `"claims"`.
Each item in `"claims"` contains:
- `id` (integer)
- `claim` (string)
- `timestamp` (string | null)

**Output Format:**
- You must return **ONLY valid JSON**.
- Do not include markdown formatting (no ```json blocks), no explanations, and no conversational text.
- The output must be a single root object containing exactly one key: `"claims"`.
- `"claims"` must be an array with one object per input item.

Each object in output `"claims"` must contain exactly:
1. `id` (integer): Copy from input item.
2. `search_query` (string): A precision PubMed query string using PICO logic.

**Query rules:**
- Use `AND` to combine concepts (Population AND Intervention AND Outcome).
- Use `OR` inside parentheses for synonyms.
- Use `*` for wildcards when useful.
- Use single quotes for multi-word phrases.
- Unless topic is extremely niche, append: `AND ('Meta Analysis'[pt] OR 'Systematic Review'[pt] OR 'Randomized Controlled Trial'[pt] OR 'Clinical Trial'[pt])`.

**Example Output Structure:**
{
  "claims": [
    {
      "id": 1,
      "search_query": "('High-Intensity Interval Training'[tiab] OR 'HIIT'[tiab]) AND 'Insulin Resistance'[tiab] AND 'Type 2 Diabetes'[tiab] AND ('Meta Analysis'[pt] OR 'Systematic Review'[pt] OR 'Randomized Controlled Trial'[pt] OR 'Clinical Trial'[pt])"
    }
  ]
}
"""

CLAIM_QUERY_USER_PROMPT = """{claims_json}"""
