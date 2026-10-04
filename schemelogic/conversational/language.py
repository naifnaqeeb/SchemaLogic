"""Deterministic language handling for the chat (multilingual stage 1, 2026-10-05). No LLM here.

The pipeline stays English internally and translates at the edges. This module does the parts that
need no model:

- `script_language`: a first guess from the script a message is written in. Latin text with no
  romanised-Hindi markers is English, and goes through the router exactly as before -- English
  behaviour is unchanged by construction. Devanagari is Hindi or Marathi; the router's own call
  decides, and `devanagari_guess` is the keyword fallback when it can't.
- `normalize_digits`: Devanagari, Arabic-Indic / Urdu and Tamil digits to ASCII.
- `yes_no`: yes/no words in the five supported languages, including romanised "haan" / "nahi".
"""

from __future__ import annotations

import re

SUPPORTED = ("en", "hi", "ur", "mr", "ta")
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "ur": "Urdu", "mr": "Marathi", "ta": "Tamil"}

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_TAMIL = re.compile(r"[஀-௿]")

# Words that are very unlikely in English and very common in romanised Hindi/Urdu chat. A message
# using two or more of them is routed as non-English; one is not enough ("ram", "bus", "sir" ...).
_ROMANISED_HINDI = frozenset({
    "haan", "haanji", "nahi", "nahin", "nahee", "kya", "mera", "meri", "mere", "mujhe", "hai", "hain", "hoon",
    "hun", "chahiye", "kaise", "kitna", "kitni", "aur", "lekin", "kyunki", "mein", "bhi", "nahi", "ghar",
    "paisa", "naukri", "kisaan", "kisan", "yojna", "batao", "bataiye", "kripya", "aap", "apna", "apni",
})
_MARATHI_MARKERS = frozenset({"आहे", "आहेत", "नाही", "माझे", "माझी", "माझा", "मी", "होय", "आणि", "काय", "करा", "मला", "तुम्ही"})


def script_language(text: str) -> str:
    """"en", "ur", "ta", "deva" (Hindi or Marathi -- see devanagari_guess) or "hi" (romanised)."""
    if _ARABIC.search(text):
        return "ur"
    if _TAMIL.search(text):
        return "ta"
    if _DEVANAGARI.search(text):
        return "deva"
    words = re.findall(r"[a-z]+", text.lower())
    if sum(1 for w in words if w in _ROMANISED_HINDI) >= 2:
        return "hi"
    return "en"


def devanagari_guess(text: str) -> str:
    words = set(re.findall(r"[ऀ-ॿ]+", text))
    return "mr" if words & _MARATHI_MARKERS else "hi"


_DIGITS = str.maketrans(
    "०१२३४५६७८९" "٠١٢٣٤٥٦٧٨٩" "۰۱۲۳۴۵۶۷۸۹" "௦௧௨௩௪௫௬௭௮௯",
    "0123456789" "0123456789" "0123456789" "0123456789",
)


def normalize_digits(text: str) -> str:
    return text.translate(_DIGITS)


_YES = frozenset({
    # Hindi / Marathi (Devanagari) and romanised Hindi
    "हाँ", "हां", "हा", "जी", "जी हाँ", "जी हां", "होय", "हो", "haan", "haanji", "haa", "han ji", "haan ji", "ji haan",
    # Urdu
    "ہاں", "جی", "جی ہاں", "ہاں جی",
    # Tamil
    "ஆம்", "ஆமாம்",
})
_NO = frozenset({
    "नहीं", "नही", "ना", "जी नहीं", "नाही", "nahi", "nahin", "nahee", "nai", "ji nahi", "nahi ji",
    "نہیں", "جی نہیں", "نا",
    "இல்லை", "கிடையாது",
})


def yes_no(raw: str) -> bool | None:
    """True / False for a yes / no word in a supported language, None if it isn't one. English yes/no
    is handled by the caller exactly as before."""
    text = " ".join(raw.strip().lower().strip(".!?।۔").split())
    if text in _YES:
        return True
    if text in _NO:
        return False
    return None
