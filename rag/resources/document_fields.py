"""Reading the fields of a web API's JSON answer and writing them as the labelled lines of a text document."""

from collections.abc import Iterable
from typing import Any

LINE_FORMAT = "{label}: {value}"
NAME_SEPARATOR = ", "
LINE_SEPARATOR = "\n"
# Joins the counts in a read summary.
SUMMARY_SEPARATOR = ", "


def json_entries(entries: Any) -> list[dict[str, Any]]:
    """The objects of a JSON list; anything else is an empty list."""
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def unique_names(entries: Iterable[dict[str, Any]]) -> list[str]:
    """Each entry's name once, in the answer's order."""
    return list(dict.fromkeys(name for name in (clean_text(entry.get("name")) for entry in entries) if name))


def join_names(names: list[str]) -> str:
    return NAME_SEPARATOR.join(names)


def labelled_lines(*labelled_values: tuple[str, str]) -> list[str]:
    """One line per value; a line without a value is left out."""
    return [LINE_FORMAT.format(label=label, value=value) for label, value in labelled_values if value]


def clean_text(value: Any) -> str:
    """A text value without its outer spaces; anything else is empty text."""
    return value.strip() if isinstance(value, str) else ""
