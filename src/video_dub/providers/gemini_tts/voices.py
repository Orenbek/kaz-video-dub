from __future__ import annotations

GEMINI_TTS_VOICE_NAMES = (
    "Zephyr",
    "Puck",
    "Charon",
    "Kore",
    "Fenrir",
    "Leda",
    "Orus",
    "Aoede",
    "Callirrhoe",
    "Autonoe",
    "Enceladus",
    "Iapetus",
    "Umbriel",
    "Algieba",
    "Despina",
    "Erinome",
    "Algenib",
    "Rasalgethi",
    "Laomedeia",
    "Achernar",
    "Alnilam",
    "Schedar",
    "Gacrux",
    "Pulcherrima",
    "Achird",
    "Zubenelgenubi",
    "Vindemiatrix",
    "Sadachbia",
    "Sadaltager",
    "Sulafat",
)


def validate_voice_name(voice_name: str) -> None:
    if voice_name in GEMINI_TTS_VOICE_NAMES:
        return
    supported = ", ".join(GEMINI_TTS_VOICE_NAMES)
    raise RuntimeError(
        f"Unsupported Gemini TTS voice_name {voice_name!r}. Supported values: {supported}"
    )
