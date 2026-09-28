from __future__ import annotations

import importlib.util
from pathlib import Path

BASE_PATH = Path(__file__).with_name("generate_v2_6_0_firmware.py")
_spec = importlib.util.spec_from_file_location("v260_base_generator", BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_base)


def _find_function_definition(text: str, signature: str) -> tuple[int, int, int]:
    """Find a C++ function definition, deliberately skipping forward declarations."""
    search_from = 0
    while True:
        start = text.find(signature, search_from)
        if start < 0:
            raise ValueError(f"function definition not found: {signature}")
        brace = text.find("{", start)
        semicolon = text.find(";", start)
        if brace < 0:
            raise ValueError(f"opening brace not found: {signature}")
        if semicolon >= 0 and semicolon < brace:
            search_from = semicolon + 1
            continue

        depth = 0
        in_string: str | None = None
        escape = False
        line_comment = False
        block_comment = False
        i = brace
        while i < len(text):
            c = text[i]
            n = text[i + 1] if i + 1 < len(text) else ""
            if line_comment:
                if c == "\n":
                    line_comment = False
                i += 1
                continue
            if block_comment:
                if c == "*" and n == "/":
                    block_comment = False
                    i += 2
                    continue
                i += 1
                continue
            if in_string is not None:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == in_string:
                    in_string = None
                i += 1
                continue
            if c == "/" and n == "/":
                line_comment = True
                i += 2
                continue
            if c == "/" and n == "*":
                block_comment = True
                i += 2
                continue
            if c in ('"', "'"):
                in_string = c
                i += 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return start, brace, i + 1
            i += 1
        raise ValueError(f"unterminated function definition: {signature}")


_base._find_function_end = _find_function_definition
_base.BOARD_BLOCK = _base.BOARD_BLOCK.replace("E32N35T", "legacy fallback")
_original_transform = _base._transform_source


def _transform_source(source: str) -> str:
    # Remove only obsolete source-language before the canonical board/session
    # transformation. This does not alter runtime capture behavior.
    source = source.replace("E32N35T", "E32R35T")
    source = source.replace(
        "They are intentionally profile-gated and labelled PROBABLE in SIGNALS.CSV.",
        "They are intentionally profile-gated and labelled PROBABLE in the offline signal registry.",
    )
    return _original_transform(source)


_base._transform_source = _transform_source


def generate(rc2_dir: Path | str, out_root: Path | str) -> Path:
    return _base.generate(rc2_dir, out_root)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("rc2_dir", type=Path)
    parser.add_argument("out_root", type=Path)
    args = parser.parse_args()
    print(generate(args.rc2_dir, args.out_root))
