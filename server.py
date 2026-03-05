"""
json_suppressor MCP Server
Exposes a single tool: validate(input, mode)

Modes:
  strict  - parse JSON as-is; any syntax error is a violation
  lenient - try simple repairs if parsing fails; coerce string-encoded scalars
  extract - locate the first JSON object/array in arbitrary text, then strict-parse it
"""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("json_suppressor")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repair_json(text: str) -> tuple[str, list[str]]:
    """
    Attempt simple textual repairs on a malformed JSON string.
    Returns (repaired_text, list_of_repair_violation_strings).
    """
    repairs: list[str] = []

    # 1. Remove trailing commas before } or ]
    repaired = re.sub(r',(\s*[}\]])', r'\1', text)
    if repaired != text:
        repairs.append("trailing_comma: removed trailing comma(s) before } or ]")
        text = repaired

    # 2. Quote unquoted object keys  (bare word immediately followed by :)
    repaired = re.sub(
        r'(?<=[{,])\s*([A-Za-z_]\w*)\s*:',
        lambda m: f' "{m.group(1)}":',
        text,
    )
    if repaired != text:
        repairs.append("unquoted_keys: added quotes around unquoted object key(s)")
        text = repaired

    return text, repairs


def _coerce_values(data: Any, violations: list[str], path: str = "root") -> Any:
    """
    Walk parsed data and heuristically coerce string values that look like
    numbers or booleans into their native Python/JSON types.
    Appends a violation entry for each coercion performed.
    """
    if isinstance(data, dict):
        return {k: _coerce_values(v, violations, f"{path}.{k}") for k, v in data.items()}
    if isinstance(data, list):
        return [_coerce_values(item, violations, f"{path}[{i}]") for i, item in enumerate(data)]
    if isinstance(data, str):
        low = data.lower()
        if low == "true":
            violations.append(f"{path}: coerced string 'true' to boolean true")
            return True
        if low == "false":
            violations.append(f"{path}: coerced string 'false' to boolean false")
            return False
        # Integer (no decimal point, optional leading minus)
        if re.fullmatch(r"-?\d+", data):
            v = int(data)
            violations.append(f"{path}: coerced string '{data}' to integer {v}")
            return v
        # Float
        if re.fullmatch(r"-?\d+\.\d*([eE][+-]?\d+)?|-?\d*\.\d+([eE][+-]?\d+)?", data):
            v = float(data)
            violations.append(f"{path}: coerced string '{data}' to float {v}")
            return v
    return data


def _extract_json_text(text: str) -> str | None:
    """
    Return the first JSON object or array found in *text*, or None.

    Search order:
      1. Content of a ```json … ``` or ``` … ``` code fence whose body
         starts with { or [.
      2. First balanced { … } block in the raw text.
      3. First balanced [ … ] block in the raw text.
    """
    # 1. Code fence
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.startswith(("{", "[")):
            return candidate

    # 2 & 3. Balanced brace / bracket scan
    for start_ch, end_ch in [("{", "}"), ("[", "]")]:
        idx = text.find(start_ch)
        if idx == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(idx, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_ch:
                depth += 1
            elif ch == end_ch:
                depth -= 1
                if depth == 0:
                    return text[idx : i + 1]

    return None


# ---------------------------------------------------------------------------
# MCP tool
# ---------------------------------------------------------------------------

@mcp.tool()
def validate(
    input: str,
    mode: str = "strict",
) -> dict:
    """
    Parse, repair, or extract JSON from a text string.

    Parameters
    ----------
    input : str
        The raw text to process. For strict/lenient this should already be a
        JSON string. For extract it may be any text (prose, markdown, code
        fences) that contains an embedded JSON object or array.
    mode : str, optional
        - "strict"  (default): call json.loads() directly. Any syntax error
          becomes a parse_error violation and clean_data is null.
        - "lenient" : if parsing fails, try simple repairs (remove trailing
          commas, quote bare keys). Repairs are reported as violations. After
          a successful parse, string-encoded numbers and booleans are coerced
          to their native types (also reported as violations).
        - "extract" : locate the first JSON object or array anywhere in the
          text (including inside markdown code fences or prose), then run
          strict mode on the extracted fragment. Returns extract_error if
          nothing is found.

    Returns
    -------
    dict with keys:
        mode_used  : the mode that was applied ("strict", "lenient", or "extract")
        clean_data : the parsed / repaired object or array, or null on failure
        violations : list of issue/repair strings; empty means fully clean
    """
    mode = mode.strip().lower()
    if mode not in ("strict", "lenient", "extract"):
        return {
            "mode_used": mode,
            "clean_data": None,
            "violations": [
                f"unknown_mode: '{mode}' is not valid — use strict, lenient, or extract"
            ],
        }

    # ------------------------------------------------------------------
    # STRICT
    # ------------------------------------------------------------------
    if mode == "strict":
        try:
            clean_data = json.loads(input)
            return {"mode_used": "strict", "clean_data": clean_data, "violations": []}
        except json.JSONDecodeError as exc:
            return {
                "mode_used": "strict",
                "clean_data": None,
                "violations": [f"parse_error: {exc}"],
            }

    # ------------------------------------------------------------------
    # LENIENT
    # ------------------------------------------------------------------
    if mode == "lenient":
        violations: list[str] = []

        # First attempt: straight parse
        try:
            clean_data = json.loads(input)
        except json.JSONDecodeError as initial_err:
            # Attempt textual repairs
            repaired, repairs = _repair_json(input)
            if not repairs:
                # Nothing could be repaired
                return {
                    "mode_used": "lenient",
                    "clean_data": None,
                    "violations": [f"parse_error: {initial_err}"],
                }
            violations.extend(repairs)
            try:
                clean_data = json.loads(repaired)
            except json.JSONDecodeError as exc:
                return {
                    "mode_used": "lenient",
                    "clean_data": None,
                    "violations": violations + [f"parse_error: {exc}"],
                }

        # Heuristic scalar coercion on the successfully-parsed data
        clean_data = _coerce_values(clean_data, violations)
        return {"mode_used": "lenient", "clean_data": clean_data, "violations": violations}

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    # mode == "extract"
    extracted = _extract_json_text(input)
    if extracted is None:
        return {
            "mode_used": "extract",
            "clean_data": None,
            "violations": ["extract_error: no JSON object or array found in input"],
        }

    try:
        clean_data = json.loads(extracted)
        return {"mode_used": "extract", "clean_data": clean_data, "violations": []}
    except json.JSONDecodeError as exc:
        return {
            "mode_used": "extract",
            "clean_data": None,
            "violations": [f"parse_error: {exc}"],
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
