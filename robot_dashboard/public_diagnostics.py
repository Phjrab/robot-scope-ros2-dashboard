"""Bound internal diagnostics before exposing them through browser APIs."""

from __future__ import annotations

import re


PUBLIC_DIAGNOSTIC_MESSAGE_CHARS = 320
PUBLIC_DIAGNOSTIC_INPUT_CHARS = 4096

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_CONTROL_CHARACTER_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")
_ROS_LOG_RE = re.compile(
    r"^\[(DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\]\s*"
    r"(?:\[[0-9]{1,20}(?:\.[0-9]{1,12})?\]\s*)?"
    r"\[([A-Za-z][A-Za-z0-9_.-]{0,63})\]:\s*(.*)$",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|"
    r"private[_-]?key|credential|authorization|bridge[_-]?key)[A-Za-z0-9_]*)"
    r"\b\s*(?:[:=]|\s)\s*"
    r"(?:\"[^\"]*\"|'[^']*'|\S+)"
)
_JSON_SECRET_RE = re.compile(
    r"(?i)([\"'][^\"']*(?:password|passwd|secret|token|api[_-]?key|"
    r"private[_-]?key|credential|authorization|bridge[_-]?key)"
    r"[^\"']*[\"']\s*:\s*)(?:\"[^\"]*\"|'[^']*'|[^,}\]\s]+)"
)
_ENV_DUMP_RE = re.compile(r"(?i)\benv(?:iron(?:ment)?)?\s*[:=]\s*[\[{].*$")
_AUTH_VALUE_RE = re.compile(r"(?i)\b(?:Bearer|Basic)\s+\S+")
_ENV_ASSIGNMENT_RE = re.compile(r"\b([A-Z][A-Z0-9_]{1,63})\s*=\s*\S+")
_URL_RE = re.compile(r"(?i)\b(?:https?|file|ssh)://\S+")
_WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:[\\/][^\s'\"<>]+")
_HOME_PATH_RE = re.compile(r"(?:^|(?<=\s))~[/\\][^\s'\"<>]+")
_RELATIVE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:\.{1,2}[/\\]|[A-Za-z0-9_.-]+[/\\])"
    r"[^\s'\"<>]+"
)
_ABSOLUTE_PATH_OR_TOPIC_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s'\"<>]+)")
_FILE_NAME_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])[^\s'\"<>/\\]+\."
    r"(?:yaml|yml|pgm|pcd|json|py|sh|xml|db3|sqlite3|bag|log)"
    r"(?![A-Za-z0-9_.-])"
)
_LONG_HEX_RE = re.compile(r"(?i)\b[0-9a-f]{24,}\b")
_COMMAND_DETAIL_RE = re.compile(
    r"(?i)(?:\bargv\b|\bcommand(?:\s+line)?\b|\bexec(?:ute|uting|uted)?\b)"
    r"\s*(?:[:=]|\[)"
)
_INTERPRETER_COMMAND_RE = re.compile(
    r"(?i)(?:^|\s)(?:ros2|python\d*(?:\.\d+)?|bash|sh)\s+"
    r"(?:run|launch|-[A-Za-z]|[^\s]+)"
)
_CLI_ARGUMENT_RE = re.compile(r"(?<![A-Za-z0-9_])--[A-Za-z][A-Za-z0-9_-]*")


def public_diagnostic(message: object, *, runtime: bool = False) -> str:
    """Return one bounded, redacted diagnostic safe for browser projection.

    Runtime child output is untrusted. Only standard ROS log envelopes and the
    repository launcher's fixed prefix retain payload text; other child lines
    become a generic event. Internal exception messages retain useful text but
    never paths, URLs, credentials, command details, control bytes, or long
    opaque identifiers.
    """

    raw = _ANSI_ESCAPE_RE.sub("", str(message or "")[:PUBLIC_DIAGNOSTIC_INPUT_CHARS])
    raw = _CONTROL_CHARACTER_RE.sub("", raw).replace("\r", " ").replace("\n", " ")
    raw = _WHITESPACE_RE.sub(" ", raw).strip()
    if not raw:
        return ""

    prefix = ""
    payload = raw
    if runtime:
        ros = _ROS_LOG_RE.fullmatch(raw)
        if ros:
            severity = ros.group(1).upper().replace("WARNING", "WARN")
            logger_name = ros.group(2)[:64]
            prefix = f"{severity} {logger_name}: "
            payload = ros.group(3)
        elif raw.startswith("[Robot Scope] "):
            prefix = "Robot Scope: "
            payload = raw[len("[Robot Scope] ") :]
        else:
            return "runtime output received"

    if (
        _COMMAND_DETAIL_RE.search(payload)
        or _INTERPRETER_COMMAND_RE.search(payload)
        or _CLI_ARGUMENT_RE.search(payload)
    ):
        return (
            f"{prefix}runtime command detail withheld"
        )[:PUBLIC_DIAGNOSTIC_MESSAGE_CHARS]
    payload = _ENV_DUMP_RE.sub("environment=[redacted]", payload)
    payload = _JSON_SECRET_RE.sub(
        lambda match: f'{match.group(1)}"[redacted]"', payload
    )
    payload = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]", payload
    )
    payload = _AUTH_VALUE_RE.sub("authorization=[redacted]", payload)
    payload = _ENV_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]", payload
    )
    payload = _URL_RE.sub("[url]", payload)
    payload = _WINDOWS_PATH_RE.sub("[path]", payload)
    payload = _HOME_PATH_RE.sub(" [path]", payload)
    payload = _RELATIVE_PATH_RE.sub("[path]", payload)
    payload = _ABSOLUTE_PATH_OR_TOPIC_RE.sub("[path-or-topic]", payload)
    payload = _FILE_NAME_RE.sub("[file]", payload)
    payload = _LONG_HEX_RE.sub("[id]", payload)
    payload = _WHITESPACE_RE.sub(" ", payload).strip()
    if not payload:
        payload = "diagnostic detail withheld"
    return f"{prefix}{payload}"[:PUBLIC_DIAGNOSTIC_MESSAGE_CHARS]
