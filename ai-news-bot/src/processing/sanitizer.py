from __future__ import annotations

import re


_PREAMBLE_PATTERNS = [
    re.compile(r"^(Here is|Here are|Let me|I will|I'll|Sure|Okay|Of course)[^\n]*\n?", re.IGNORECASE),
    re.compile(r"^(Based on|Looking at|Analyzing)[^\n]*\n?", re.IGNORECASE),
]

_REASONING_TAGS = re.compile(r"<\|?(?:thinking|reasoning|reflect)\|?>.*?</\|?(?:thinking|reasoning|reflect)\|?>", re.DOTALL)

_CODE_FENCES = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def sanitize_llm_output(text: str) -> str:
    text = _REASONING_TAGS.sub("", text)

    fence_match = _CODE_FENCES.search(text)
    if fence_match:
        text = fence_match.group(1)

    for pattern in _PREAMBLE_PATTERNS:
        text = pattern.sub("", text)

    return text.strip()
