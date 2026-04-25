from __future__ import annotations

"""
Built-in job templates for the headless API.

Each template defines:
- id:             unique slug
- name:           human-readable name
- description:    what the template does
- defaults:       base HeadlessJobCreate payload (as dict)
- required_props: placeholder keys the caller MUST supply
- optional_props: placeholder keys with fallback values in ``defaults``
"""

from typing import Any

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "quick_explainer": {
        "id": "quick_explainer",
        "name": "Quick Explainer",
        "description": "60-second explainer video on any topic with bold captions and Edge-TTS.",
        "required_props": ["topic"],
        "optional_props": ["tone", "voice_id", "target_platform"],
        "defaults": {
            "mode": "auto",
            "title": "Explainer: {{topic}}",
            "script": {
                "topic": "{{topic}}",
                "tone": "{{tone|educational}}",
                "duration_seconds": 60,
                "target_platform": "{{target_platform|tiktok}}",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "{{voice_id|en-US-JennyNeural}}",
                "rate": "+5%",
            },
            "caption": {"enabled": True, "style": "bold"},
            "video": {"background_music": True, "background_music_volume": 0.1},
            "upload": {"destinations": ["local"]},
        },
        "example_props": {
            "topic": "How does quantum computing work?",
            "tone": "educational",
            "voice_id": "en-US-JennyNeural",
            "target_platform": "youtube",
        },
    },
    "product_review": {
        "id": "product_review",
        "name": "Product Review",
        "description": "Short product review video with a hook, pros/cons, and CTA.",
        "required_props": ["product_name", "pros", "cons"],
        "optional_props": ["cta", "voice_id"],
        "defaults": {
            "mode": "semi_auto",
            "title": "{{product_name}} Review",
            "script": {
                "topic": "Review of {{product_name}}. Pros: {{pros}}. Cons: {{cons}}. {{cta|Check the link in bio.}}",
                "tone": "conversational",
                "duration_seconds": 45,
                "target_platform": "tiktok",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "{{voice_id|en-US-GuyNeural}}",
                "rate": "+8%",
            },
            "caption": {"enabled": True, "style": "boxed"},
            "video": {"background_music": False, "watermark": True},
            "upload": {"destinations": ["local"]},
        },
        "example_props": {
            "product_name": "AirPods Pro",
            "pros": "great noise cancellation, comfortable fit",
            "cons": "expensive, case scratches easily",
            "cta": "Would you buy them? Comment below!",
        },
    },
    "news_summary": {
        "id": "news_summary",
        "name": "News Summary",
        "description": "30-second news summary with karaoke-style captions.",
        "required_props": ["headline", "summary"],
        "optional_props": ["source", "voice_id"],
        "defaults": {
            "mode": "semi_auto",
            "title": "News: {{headline}}",
            "script": {
                "text": "Breaking news. {{headline}}. Here is what you need to know. {{summary}}. Source: {{source|Various}}.",
                "duration_seconds": 30,
                "target_platform": "instagram",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "{{voice_id|en-US-AriaNeural}}",
                "rate": "+10%",
            },
            "caption": {"enabled": True, "style": "karaoke"},
            "video": {"background_music": True, "background_music_volume": 0.05},
            "upload": {"destinations": ["local"]},
        },
        "example_props": {
            "headline": "AI passes bar exam with top scores",
            "summary": "A new AI model scored in the top 10 percent of all bar exam takers this year.",
            "source": "Reuters",
        },
    },
    "tutorial": {
        "id": "tutorial",
        "name": "Step-by-Step Tutorial",
        "description": "Numbered step tutorial video ideal for how-to content.",
        "required_props": ["skill", "steps"],
        "optional_props": ["target_audience", "voice_id"],
        "defaults": {
            "mode": "semi_auto",
            "title": "How to {{skill}}",
            "script": {
                "topic": "Step by step tutorial on how to {{skill}} for {{target_audience|beginners}}. Steps: {{steps}}.",
                "tone": "instructional",
                "duration_seconds": 90,
                "target_platform": "youtube",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "{{voice_id|en-US-JennyNeural}}",
                "rate": "+0%",
            },
            "caption": {"enabled": True, "style": "basic"},
            "video": {"background_music": False, "thumbnail": True},
            "upload": {"destinations": ["local"]},
        },
        "example_props": {
            "skill": "set up a Python virtual environment",
            "steps": "1. Install Python. 2. Run python -m venv env. 3. Activate it. 4. Install packages.",
            "target_audience": "developers",
        },
    },
    "story_hook": {
        "id": "story_hook",
        "name": "Story Hook",
        "description": "Attention-grabbing story opener designed to stop the scroll.",
        "required_props": ["hook", "story"],
        "optional_props": ["cta", "voice_id"],
        "defaults": {
            "mode": "full_control",
            "title": "Story: {{hook[:50]}}",
            "script": {
                "text": "{{hook}} {{story}} {{cta|Follow for more stories like this.}}",
                "duration_seconds": 45,
                "target_platform": "tiktok",
            },
            "voice": {
                "provider": "edge_tts",
                "voice_id": "{{voice_id|en-US-SaraNeural}}",
                "rate": "+12%",
                "pitch": "+2Hz",
            },
            "caption": {"enabled": True, "style": "bold"},
            "video": {"background_music": True, "background_music_volume": 0.2},
            "upload": {"destinations": ["local"]},
        },
        "example_props": {
            "hook": "I lost everything in 30 days.",
            "story": "Here is exactly how I rebuilt from zero using one simple habit.",
            "cta": "Save this if you needed to hear it.",
        },
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_templates() -> list[dict[str, Any]]:
    """Return all template metadata (without full defaults)."""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "required_props": t["required_props"],
            "optional_props": t["optional_props"],
            "example_props": t["example_props"],
        }
        for t in _TEMPLATES.values()
    ]


def get_template(template_id: str) -> dict[str, Any] | None:
    return _TEMPLATES.get(template_id)


def render_template(template_id: str, props: dict[str, Any]) -> dict[str, Any]:
    """
    Render a template by substituting ``{{key}}`` and ``{{key|default}}``
    placeholders with values from *props*.

    Returns a merged payload dict suitable for passing to HeadlessJobCreate.
    Raises ValueError if required props are missing.
    """
    import copy
    import re

    tmpl = _TEMPLATES.get(template_id)
    if tmpl is None:
        raise ValueError(f"Unknown template '{template_id}'")

    # Validate required props
    missing = [k for k in tmpl["required_props"] if k not in props]
    if missing:
        raise ValueError(f"Missing required props for template '{template_id}': {missing}")

    payload = copy.deepcopy(tmpl["defaults"])

    def _substitute(value: Any) -> Any:
        if isinstance(value, str):
            # Replace {{key|default}} then {{key}}
            def replacer(m: re.Match) -> str:
                key_part = m.group(1)
                if "|" in key_part:
                    key, default = key_part.split("|", 1)
                else:
                    key, default = key_part, ""
                # Handle simple slicing like {{hook[:50]}}
                slice_match = re.match(r"^(\w+)\[(.+)\]$", key)
                if slice_match:
                    real_key = slice_match.group(1)
                    raw = str(props.get(real_key, default))
                    try:
                        slice_expr = slice_match.group(2)
                        # Only support [:N] form for safety
                        n = int(slice_expr.lstrip(":"))
                        return raw[:n]
                    except Exception:
                        return raw
                return str(props.get(key, default))

            return re.sub(r"\{\{([^}]+)\}\}", replacer, value)
        if isinstance(value, dict):
            return {k: _substitute(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_substitute(i) for i in value]
        return value

    return _substitute(payload)
