"""Voices and accents for kai's speech.

Voices are Gemini's prebuilt voices. Gemini Live has no accent setting and picks
the language itself, so accents are requested through the system instruction.
"""

from __future__ import annotations

# (name, style) as documented by Google.
VOICES: list[tuple[str, str]] = [
    ("Zephyr", "Bright"), ("Puck", "Upbeat"), ("Charon", "Informative"), ("Kore", "Firm"),
    ("Fenrir", "Excitable"), ("Leda", "Youthful"), ("Orus", "Firm"), ("Aoede", "Breezy"),
    ("Callirrhoe", "Easy-going"), ("Autonoe", "Bright"), ("Enceladus", "Breathy"),
    ("Iapetus", "Clear"), ("Umbriel", "Easy-going"), ("Algieba", "Smooth"),
    ("Despina", "Smooth"), ("Erinome", "Clear"), ("Algenib", "Gravelly"),
    ("Rasalgethi", "Informative"), ("Laomedeia", "Upbeat"), ("Achernar", "Soft"),
    ("Alnilam", "Firm"), ("Schedar", "Even"), ("Gacrux", "Mature"), ("Pulcherrima", "Forward"),
    ("Achird", "Friendly"), ("Zubenelgenubi", "Casual"), ("Vindemiatrix", "Gentle"),
    ("Sadachbia", "Lively"), ("Sadaltager", "Knowledgeable"), ("Sulafat", "Warm"),
]

AUTO = "auto"
CUSTOM = "custom"

# key -> (label, language, region). Accent applies when kai speaks that language.
ACCENTS: dict[str, tuple[str, str, str]] = {
    "es-ES": ("Spanish — Spain", "Spanish", "Spain (Castilian Spanish, as spoken in Madrid)"),
    "es-MX": ("Spanish — Mexico", "Spanish", "Mexico"),
    "es-AR": ("Spanish — Argentina", "Spanish", "Argentina (Rioplatense Spanish)"),
    "es-CO": ("Spanish — Colombia", "Spanish", "Colombia (Bogotá)"),
    "es-CL": ("Spanish — Chile", "Spanish", "Chile"),
    "es-AN": ("Spanish — Andalusia", "Spanish", "Andalusia, Spain"),
    "es-CN": ("Spanish — Canary Islands", "Spanish", "the Canary Islands, Spain"),
    "ca-ES": ("Catalan", "Catalan", "Catalonia"),
    "en-US": ("English — United States", "English", "the United States (General American)"),
    "en-GB": ("English — United Kingdom", "English", "southern England (Received Pronunciation)"),
    "en-AU": ("English — Australia", "English", "Australia"),
    "en-IE": ("English — Ireland", "English", "Ireland"),
    "pt-PT": ("Portuguese — Portugal", "Portuguese", "Portugal (European Portuguese)"),
    "pt-BR": ("Portuguese — Brazil", "Portuguese", "Brazil"),
    "fr-FR": ("French — France", "French", "France (Paris)"),
    "fr-CA": ("French — Canada", "French", "Quebec, Canada"),
}


def accent_instruction(accent: str, custom: str = "") -> str:
    """The system-instruction line that asks for an accent, or '' for automatic."""
    if accent == CUSTOM and custom.strip():
        return f"Voice and accent preference from the user: {custom.strip()}"
    if accent in ACCENTS:
        _, language, region = ACCENTS[accent]
        return (f"When you speak {language}, always use the natural accent, pronunciation "
                f"and everyday vocabulary of {region}. Keep this accent for the whole "
                "conversation.")
    return ""
