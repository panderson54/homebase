"""Thin, reusable wrapper around the Claude API for JSON-structured lookups.
Not appliance/vendor-specific — any feature that wants to ask Claude a
question (optionally with an image) and get back a JSON object can import
this. Every failure mode (no API key configured, network/API error,
non-JSON response) returns None rather than raising, so callers can treat
an AI-powered feature as best-effort and degrade gracefully instead of
breaking the page it's attached to.
"""
import base64
import json
import logging
import os

logger = logging.getLogger(__name__)

MODEL = 'claude-opus-5'


def _client():
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def _strip_code_fence(text):
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else ''
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]
    return text.strip()


def ask_json(system_prompt, user_text=None, image_bytes=None, image_media_type='image/jpeg', max_tokens=1024):
    """Ask Claude to answer as a single JSON object; returns the parsed dict,
    or None if the API key isn't configured, the call fails, or the response
    isn't valid JSON."""
    client = _client()
    if client is None:
        return None

    content = []
    if image_bytes is not None:
        content.append({
            'type': 'image',
            'source': {
                'type': 'base64',
                'media_type': image_media_type,
                'data': base64.standard_b64encode(image_bytes).decode('utf-8'),
            },
        })
    content.append({'type': 'text', 'text': user_text or ''})

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            output_config={'effort': 'low'},
            messages=[{'role': 'user', 'content': content}],
        )
    except Exception:
        # Best-effort integration: any API/network failure should degrade to
        # "couldn't look it up", never break the page that triggered it.
        logger.exception('Anthropic API call failed')
        return None

    text = next((block.text for block in response.content if block.type == 'text'), '')
    try:
        return json.loads(_strip_code_fence(text))
    except (json.JSONDecodeError, TypeError):
        logger.warning('Anthropic response was not valid JSON: %r', text[:200])
        return None
