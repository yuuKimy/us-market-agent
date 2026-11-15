"""Heuristic prompt-injection signals in untrusted news text (not a verdict)."""

from __future__ import annotations

import re
from dataclasses import dataclass

SCANNER_VERSION = "1"

SEVERITIES = ("none", "low", "medium", "high", "critical")
_SEVERITY_RANK = {name: i for i, name in enumerate(SEVERITIES)}

_DATA_START = "<<<DATA"
_DATA_END = "DATA"

# (rule_id, severity, compiled pattern)
_RULES: list[tuple[str, str, re.Pattern[str]]] = [
  (
      "ignore_prior_instructions",
      "critical",
      re.compile(
          r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions|"
          r"disregard\s+(all\s+)?(previous|prior|above)|"
          r"forget\s+(all\s+)?(previous|prior)\s+",
          re.IGNORECASE,
      ),
  ),
  (
      "role_override",
      "critical",
      re.compile(
          r"\byou\s+are\s+now\b|"
          r"(^|\n)\s*system\s*:|"
          r"(^|\n)\s*assistant\s*:|"
          r"\bnew\s+instructions?\b|"
          r"以前の指示を無視|前の指示を無視|システムプロンプト|新しい指示",
          re.IGNORECASE,
      ),
  ),
  (
      "agent_tool_directive",
      "critical",
      re.compile(
          r"\b(run|execute)\s+(the\s+)?(shell\s+)?command\b|"
          r"\btool[_\s-]?call\b|"
          r"\bcall\s+function\b|"
          r"\bignore\s+all\s+safety\b|"
          r"\bdo\s+not\s+follow\s+(the\s+)?(rules|policy)\b",
          re.IGNORECASE,
      ),
  ),
  (
      "fake_chatml",
      "high",
      re.compile(r'\{\s*"role"\s*:\s*"(system|assistant|tool)"', re.IGNORECASE),
  ),
  (
      "markdown_fence_block",
      "high",
      re.compile(r"(^|\n)```[^\n]*$", re.MULTILINE),
  ),
  (
      "bidi_override",
      "medium",
      re.compile(r"[\u202a-\u202e\u2066-\u2069]"),
  ),
  (
      "zero_width",
      "medium",
      re.compile(r"[\u200b-\u200f\ufeff]"),
  ),
  (
      "urgent_execute",
      "medium",
      re.compile(
          r"IMPORTANT[^\n]{0,40}\b(must|required|always)\b[^\n]{0,60}\b(execute|run|ignore)\b|"
          r"必ず実行|指示に従",
          re.IGNORECASE,
      ),
  ),
  (
      "cursor_product_hook",
      "low",
      re.compile(r"\b(cursor|composer)\s+(agent|ide)\b", re.IGNORECASE),
  ),
]


@dataclass(frozen=True)
class ScanResult:
    max_severity: str
    rules: tuple[str, ...]

    def to_json_obj(self) -> dict[str, object]:
        return {"max_severity": self.max_severity, "rules": list(self.rules)}


def _max_severity(matches: list[tuple[str, str]]) -> str:
    if not matches:
        return "none"
    best = max(matches, key=lambda m: _SEVERITY_RANK[m[1]])
    return best[1]


def scan_text(text: str | None) -> ScanResult:
    if not text or not str(text).strip():
        return ScanResult("none", ())
    haystack = str(text)
    hits: list[tuple[str, str]] = []
    for rule_id, severity, pattern in _RULES:
        if pattern.search(haystack):
            hits.append((rule_id, severity))
    rule_ids = tuple(dict.fromkeys(r for r, _ in hits))
    return ScanResult(_max_severity(hits), rule_ids)


def scan_article(headline: str | None, summary: str | None) -> ScanResult:
    h = scan_text(headline)
    s = scan_text(summary)
    combined: list[tuple[str, str]] = []
    for result in (h, s):
        if result.max_severity != "none":
            for rule_id in result.rules:
                sev = next(sev for rid, sev, _ in _RULES if rid == rule_id)
                combined.append((rule_id, sev))
    rule_ids = tuple(dict.fromkeys(r for r, _ in combined))
    return ScanResult(_max_severity(combined), rule_ids)


def severity_within_ceiling(severity: str, ceiling: str) -> bool:
    """True if severity is at or below ceiling (safe to emit for agent scoring)."""
    if severity not in _SEVERITY_RANK:
        severity = "none"
    if ceiling not in _SEVERITY_RANK:
        ceiling = "critical"
    return _SEVERITY_RANK[severity] <= _SEVERITY_RANK[ceiling]


def wrap_for_agent(text: str) -> str:
    """Delimit untrusted text (same convention as security-check reports)."""
    body = str(text).replace(_DATA_END, "[DATA]")
    return f"{_DATA_START}\n{body}\n{_DATA_END}"


def format_scan_lines(text: str) -> str:
    """Human-readable scan for `mkt inspect text`."""
    result = scan_text(text)
    lines = [f"scanner_version: {SCANNER_VERSION}", f"max_severity: {result.max_severity}"]
    if result.rules:
        lines.append("rules: " + ", ".join(result.rules))
    else:
        lines.append("rules: (none)")
    return "\n".join(lines)