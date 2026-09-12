"""Engine config-key schema — each mesher declares the keys it reads.

Before this module the same knob could be read from two places (``ground_refine``
and ``refinement_thickness`` were accepted in both ``mesh_params`` and
``cfmesh``), a key could be read by a writer yet never validated
(``te_level``), and the web UI carried its own copy of the defaults. A mesher now
declares every key once as a :class:`KeySpec`; validation and the UI placeholders
are generated from that declaration.

Kinds:

    BOOL           true / false
    INT            nonnegative (or positive) integer
    METRES         number in metres, > 0
    SIZE_OR_ALIAS  number in metres or one of a small set of named cells
    NUMBER         finite number
    ENUM           one of ``choices``
    TRISTATE       true / false / "auto"
    VECTOR         three finite numbers
    REGIONS        list of {name, min, max, level} refinement boxes
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

BOOL = "bool"
INT = "int"
METRES = "metres"
SIZE_OR_ALIAS = "size_or_alias"
NUMBER = "number"
ENUM = "enum"
TRISTATE = "tristate"
VECTOR = "vector"
REGIONS = "regions"
MAPPING = "mapping"
AUTO = "auto"
LEVELS = "levels"
SHELLS = "shells"


@dataclass(frozen=True)
class KeySpec:
    """One configuration key: how to validate it, and what it defaults to."""

    kind: str
    doc: str = ""
    default: Any = None
    choices: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    allow_zero: bool = False
    #: Mesher names that read this key; empty means every mesher does. Declaring
    #: it here is what tells ``validate`` (and the UI) that a key belongs to one
    #: engine, so "cfMesh ignores maxGlobalCells" has one source of truth instead
    #: of a list in the validator, a note in the docs and a docstring prefix.
    engines: tuple[str, ...] = ()

    def reads(self, engine: str) -> bool:
        return not self.engines or engine in self.engines

    def valid(self, value: Any) -> bool:
        if self.kind == BOOL:
            return isinstance(value, bool)
        if self.kind == INT:
            return _is_int(value) and (value >= 0 if self.allow_zero else value > 0)
        if self.kind in (METRES, NUMBER):
            return _is_number(value) and (value >= 0 if self.allow_zero else value > 0)
        if self.kind == SIZE_OR_ALIAS:
            if isinstance(value, str):
                return value.strip().lower() in self.aliases
            return _is_number(value) and value > 0
        if self.kind == ENUM:
            return isinstance(value, str) and value.strip().lower() in self.choices
        if self.kind == TRISTATE:
            return isinstance(value, bool) or (
                isinstance(value, str) and value.strip().lower() in ("auto", "true", "false")
            )
        if self.kind == AUTO:
            if isinstance(value, str):
                return value.strip().lower() == "auto"
            return _is_number(value) and (value >= 0 if self.allow_zero else value > 0)
        if self.kind == VECTOR:
            return (isinstance(value, (list, tuple)) and len(value) == 3
                    and all(_is_number(v) for v in value))
        if self.kind == LEVELS:
            return (isinstance(value, (list, tuple)) and len(value) == 2
                    and all(_is_int(n) and n >= 0 for n in value)
                    and value[0] <= value[1])
        if self.kind == SHELLS:
            return (isinstance(value, (list, tuple)) and all(
                isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(_is_number(v) for v in pair) for pair in value))
        if self.kind == MAPPING:
            return isinstance(value, dict)
        if self.kind == REGIONS:
            return isinstance(value, (list, tuple)) and all(_region_ok(r) for r in value)
        return True

    def describe(self) -> str:
        """Human-readable expectation, used in error messages."""
        if self.kind == BOOL:
            return "true or false"
        if self.kind == INT:
            return f"a finite integer {'>= 0' if self.allow_zero else '> 0'}"
        if self.kind == METRES:
            return "a number in metres > 0"
        if self.kind == NUMBER:
            return f"a finite number {'>= 0' if self.allow_zero else '> 0'}"
        if self.kind == SIZE_OR_ALIAS:
            return ("a number in metres or one of "
                    + ", ".join(repr(a) for a in self.aliases))
        if self.kind == ENUM:
            return "one of " + ", ".join(repr(c) for c in self.choices)
        if self.kind == TRISTATE:
            return "true, false or 'auto'"
        if self.kind == VECTOR:
            return "three finite numbers"
        if self.kind == REGIONS:
            return "a list of {name, min, max, level} boxes"
        if self.kind == MAPPING:
            return "an object"
        if self.kind == AUTO:
            return f"{'a nonnegative number' if self.allow_zero else 'a number > 0'} or 'auto'"
        if self.kind == LEVELS:
            return "two ordered nonnegative integers"
        if self.kind == SHELLS:
            return "a list of (size, level) pairs"
        return "a supported value"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return (not isinstance(value, bool)) and isinstance(value, (int, float)) and math.isfinite(value)


def _region_ok(region: Any) -> bool:
    if not isinstance(region, dict):
        return False
    name = region.get("name")
    if not isinstance(name, str) or not name or any(c.isspace() for c in name):
        return False
    for edge in ("min", "max"):
        value = region.get(edge)
        if not (isinstance(value, (list, tuple)) and len(value) == 3
                and all(_is_number(v) for v in value)):
            return False
    level = region.get("level", 0)
    return _is_int(level) and level >= 0


def validate_keys(block: dict[str, Any], specs: dict[str, KeySpec], label: str) -> list[str]:
    """Validate every declared key present in ``block``; returns error strings."""
    errors: list[str] = []
    for key, value in block.items():
        spec = specs.get(key)
        if spec is None:
            continue  # unknown keys are reported by :func:`unknown_keys`
        if not spec.valid(value):
            errors.append(f"{label}.{key} must be {spec.describe()}")
    return errors


def unknown_keys(block: dict[str, Any], specs: dict[str, KeySpec], label: str,
                 *, allowed: Iterable[str] = ()) -> list[str]:
    """Report keys nothing reads, so a typo cannot pass silently."""
    known = set(specs) | set(allowed)
    return [f"{label}.{key} is not a recognised setting"
            for key in block if key not in known]


def docs(specs: dict[str, KeySpec]) -> list[dict[str, Any]]:
    """Machine-readable key documentation for the web UI."""
    return [
        {
            "key": name,
            "kind": spec.kind,
            "default": spec.default,
            "choices": list(spec.choices),
            "engines": list(spec.engines),
            "doc": spec.doc,
        }
        for name, spec in specs.items()
    ]


def removed(block: dict[str, Any], removed_keys: dict[str, str], label: str) -> list[str]:
    """Errors for keys deleted from the surface, naming the replacement."""
    return [f"{label}.{key} was removed: {reason}"
            for key, reason in removed_keys.items() if key in block]


__all__ = [
    "KeySpec",
    "AUTO", "BOOL", "ENUM", "INT", "LEVELS", "MAPPING", "METRES", "NUMBER",
    "REGIONS", "SHELLS", "SIZE_OR_ALIAS", "TRISTATE", "VECTOR",
    "docs", "removed", "unknown_keys", "validate_keys",
]
