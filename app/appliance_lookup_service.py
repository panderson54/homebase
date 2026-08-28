"""Prefills appliance fields from a model number and/or a photo of its
nameplate, using the Anthropic API (via app.ai_client). Best-effort: never
raises, and returns whatever subset of fields Claude was confident about —
callers decide what to do with a partial or empty result.
"""
from app import ai_client
from app.category_templates_data import CATEGORY_LABELS
from app.models import FrequencyUnit

_SYSTEM_PROMPT = """You are helping identify a home appliance from its model number \
and/or a photo of its nameplate or serial-number label. Respond with ONLY a single \
JSON object (no prose, no markdown code fences) with exactly these keys. Use null \
for anything you aren't confident about — never guess.

{{
  "make": string or null,
  "category": one of [{categories}] or null,
  "model_number": string or null — read from the photo if legible and not already given,
  "serial_number": string or null — read from the photo if legible,
  "manufacture_year": integer or null — the year this unit was manufactured, inferred from the serial number if possible,
  "manual_url": string or null — a URL to the official owner's manual, only if you are confident it is correct,
  "pro_service_interval_value": integer or null,
  "pro_service_interval_unit": one of {units} or null,
  "notes": string or null — a short, useful paragraph about this specific model
}}""".format(
    categories=', '.join(sorted(CATEGORY_LABELS)),
    units=[unit.value for unit in FrequencyUnit],
)


def lookup_appliance(model_number=None, image_bytes=None, image_media_type='image/jpeg'):
    """Returns a dict of whatever appliance fields could be identified — an
    empty dict if nothing was given, the API isn't configured, or the lookup
    failed."""
    model_number = (model_number or '').strip()
    if not model_number and image_bytes is None:
        return {}

    user_text = f'Model number: {model_number}' if model_number else 'Identify this appliance from the attached photo.'
    result = ai_client.ask_json(
        _SYSTEM_PROMPT, user_text=user_text, image_bytes=image_bytes, image_media_type=image_media_type,
    )
    if not isinstance(result, dict):
        return {}

    if result.get('category') not in CATEGORY_LABELS:
        result['category'] = None
    if result.get('pro_service_interval_unit') not in FrequencyUnit.__members__:
        result['pro_service_interval_unit'] = None
    return result
