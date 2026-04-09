# Claude API Patterns for DiraDream

## SDK Setup

```python
from anthropic import Anthropic

client = Anthropic()  # Uses ANTHROPIC_API_KEY env var
```

## Structured Output for Room Classification

```python
import json

def classify_rooms_with_vision(image_base64: str, rooms_data: list) -> dict:
    """
    Use Claude Vision to cross-reference rule-based room classification.
    """
    response = client.messages.create(
        model="claude-opus-4-6-20250415",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64,
                    },
                },
                {
                    "type": "text",
                    "text": f"""Analyze this Israeli apartment floor plan image.

For each room polygon listed below, verify or correct the room type classification.

Current classifications:
{json.dumps(rooms_data, ensure_ascii=False, indent=2)}

Respond ONLY with valid JSON in this exact format:
{{
  "rooms": [
    {{
      "id": "room_1",
      "classified_type": "salon",
      "confidence": 92,
      "reasoning": "Largest room, open to kitchen area, contains living room furniture symbols"
    }}
  ],
  "apartment_summary": {{
    "total_rooms": 4,
    "room_count_israeli": "4 חדרים",
    "issues": []
  }}
}}"""
                }
            ]
        }]
    )

    # Parse defensively
    try:
        text = response.content[0].text
        # Extract JSON from response (may have markdown wrapping)
        json_start = text.index('{')
        json_end = text.rindex('}') + 1
        return json.loads(text[json_start:json_end])
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": str(e), "raw": response.content[0].text}
```

## Cost Estimation

```python
def estimate_modification_cost(modification: dict) -> dict:
    """
    Use Claude to estimate modification costs based on type and context.
    ALWAYS returns a range (min-max), NEVER a single number.
    """
    response = client.messages.create(
        model="claude-opus-4-6-20250415",
        max_tokens=1024,
        system="""You are an Israeli residential construction cost estimator.
All prices in ILS (Israeli Shekels), reflecting 2024-2026 market prices.
ALWAYS provide a range (min-max), NEVER a single number.
Include disclaimer that these are estimates only.
Consider: location factor, floor level, building age, complexity.""",
        messages=[{
            "role": "user",
            "content": f"""Estimate the cost for this apartment modification:

Modification: {json.dumps(modification, ensure_ascii=False)}

Respond ONLY with valid JSON:
{{
  "cost_min_ils": 15000,
  "cost_max_ils": 40000,
  "confidence": 75,
  "factors": [
    {{"factor": "wall_type", "impact": "standard partition, straightforward removal"}},
    {{"factor": "electrical", "impact": "may need outlet relocation, +5K-10K"}}
  ],
  "requires_permit": false,
  "permit_type": null,
  "timeline_days": "7-14",
  "disclaimer_he": "הערכת עלויות בלבד. יש לקבל הצעת מחיר מקבלן מורשה."
}}"""
        }]
    )

    return parse_json_response(response)
```

## Photo Dimension Extraction

```python
def extract_dimensions_from_photo(photo_base64: str, item_type: str) -> dict:
    """
    Estimate furniture dimensions from a user-uploaded photo.
    Flag all results as 'estimated' with confidence scores.
    """
    response = client.messages.create(
        model="claude-opus-4-6-20250415",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": photo_base64,
                    },
                },
                {
                    "type": "text",
                    "text": f"""Estimate the dimensions of this {item_type} in centimeters.
Use standard furniture proportions and any visible reference objects for scale.

Respond ONLY with valid JSON:
{{
  "width_cm": 180,
  "depth_cm": 85,
  "height_cm": 75,
  "confidence": 65,
  "source": "photo_estimate",
  "reference_used": "door frame visible, estimated 80cm standard",
  "warning_he": "המידות מבוססות על הערכה מתמונה. מומלץ למדוד ידנית."
}}"""
                }
            ]
        }]
    )

    result = parse_json_response(response)
    result['source'] = 'photo_ai'  # Always mark as AI-estimated
    return result
```

## Modification Suggestions

```python
def suggest_modifications(apartment_data: dict, dream_profile: dict) -> dict:
    """
    Suggest modifications to better match the user's dream profile.
    """
    response = client.messages.create(
        model="claude-opus-4-6-20250415",
        max_tokens=2048,
        system="""You are an Israeli apartment modification advisor.
Suggest practical modifications based on the user's dream profile.
Respect structural constraints: mamad NEVER modifiable, exterior walls need permits.
Always consider cost implications and Israeli building regulations.
Respond in Hebrew for user-facing text, English for data fields.""",
        messages=[{
            "role": "user",
            "content": f"""Current apartment:
{json.dumps(apartment_data, ensure_ascii=False, indent=2)}

User's dream profile:
{json.dumps(dream_profile, ensure_ascii=False, indent=2)}

Suggest modifications. Respond ONLY with valid JSON:
{{
  "suggestions": [
    {{
      "id": "sug_1",
      "type": "wall_remove",
      "description_he": "הסרת קיר בין מטבח לסלון ליצירת מרחב פתוח",
      "description_en": "Remove wall between kitchen and salon for open plan",
      "affected_walls": ["wall_5"],
      "affected_rooms": ["room_kitchen", "room_salon"],
      "structural_risk": "low",
      "cost_min_ils": 15000,
      "cost_max_ils": 35000,
      "priority": 1,
      "dream_match_improvement": 15
    }}
  ],
  "total_cost_range": {{ "min": 50000, "max": 120000 }},
  "disclaimer_he": "..."
}}"""
        }]
    )

    return parse_json_response(response)
```

## Defensive JSON Parsing

```python
import json
import re

def parse_json_response(response) -> dict:
    """
    Defensively parse JSON from Claude response.
    Handles markdown code blocks, extra text, malformed JSON.
    """
    text = response.content[0].text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    code_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object in text
    try:
        json_start = text.index('{')
        json_end = text.rindex('}') + 1
        return json.loads(text[json_start:json_end])
    except (ValueError, json.JSONDecodeError):
        pass

    # Return error with raw text for debugging
    return {
        "error": "PARSE_FAILED",
        "raw_response": text[:500],
        "confidence": 0
    }
```

## When NOT to Use AI

AI should NOT be used for:
- **Geometric calculations**: Use Shapely/SciPy (exact math, not probabilistic)
- **Coordinate transforms**: Use formulas (deterministic)
- **Area calculations**: Use polygon.area (exact)
- **Snap/merge/heal**: Use KDTree algorithms (exact)
- **Graph operations**: Use NetworkX (exact)

AI SHOULD be used for:
- Room classification (cross-referencing rule-based results)
- Cost estimation (requires market knowledge)
- Modification suggestions (requires domain knowledge)
- Photo dimension extraction (requires visual understanding)
- Natural language in Hebrew (error messages, descriptions)

## Error Handling

```python
from anthropic import APIError, RateLimitError, APITimeoutError

def safe_api_call(func, *args, max_retries=2, **kwargs):
    """Wrap Claude API calls with retry logic."""
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except RateLimitError:
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
        except APITimeoutError:
            if attempt < max_retries:
                continue
            raise
        except APIError as e:
            # Log error, return fallback
            return {"error": str(e), "confidence": 0}
```
