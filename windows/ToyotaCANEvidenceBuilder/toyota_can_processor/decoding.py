from __future__ import annotations

import ast
import math
import operator
import string
from typing import Any


_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Invert: operator.invert}


class FormulaError(ValueError):
    pass


def _bit(value: float | int, index: float | int) -> int:
    return (int(value) >> int(index)) & 1


def evaluate_formula(formula: str, variables: dict[str, float | int]) -> float | int:
    """Evaluate the database's arithmetic formula subset without using eval()."""

    def visit(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name) and node.id in variables:
            return variables[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](visit(node.operand))
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "bit" and len(node.args) == 2 and not node.keywords):
            return _bit(visit(node.args[0]), visit(node.args[1]))
        raise FormulaError(f"Unsupported formula expression: {ast.dump(node, include_attributes=False)}")

    try:
        value = visit(ast.parse(str(formula), mode="eval"))
    except (SyntaxError, ArithmeticError, TypeError) as error:
        raise FormulaError(f"Invalid formula {formula!r}: {error}") from error
    if isinstance(value, float) and not math.isfinite(value):
        raise FormulaError(f"Non-finite formula result for {formula!r}")
    return value


def _prefix(definition: dict[str, Any]) -> bytes:
    value = str(definition.get("response_prefix", ""))
    return bytes.fromhex(value) if value else b""


def _field_variables(data: bytes, raw: int, signed: int) -> dict[str, float | int]:
    variables: dict[str, float | int] = {
        "raw": raw,
        "uint8": raw,
        "uint16": raw,
        "uint24": raw,
        "uint32": raw,
        "int8": signed,
        "int16": signed,
        "int24": signed,
        "int32": signed,
    }
    for index, name in enumerate(string.ascii_uppercase):
        if index < len(data):
            variables[name] = data[index]
    return variables


def _quality(value: float | int | str, item: dict[str, Any], definition: dict[str, Any],
             *, inherit_definition_bounds: bool = False) -> tuple[str, str]:
    expected_status = ""
    if "expected" in item:
        expected_status = "MATCH" if value == item["expected"] else "MISMATCH"
    bounds = item.get("bounds") or (definition.get("bounds") if inherit_definition_bounds else None)
    bounds_status = ""
    if bounds and isinstance(value, (int, float)):
        minimum = bounds.get("minimum")
        maximum = bounds.get("maximum")
        bounds_status = "PASS"
        if minimum is not None and value < float(minimum):
            bounds_status = "FAIL_LOW"
        if maximum is not None and value > float(maximum):
            bounds_status = "FAIL_HIGH"
    return bounds_status, expected_status


def decode_field(data: bytes, item: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    offset = int(item.get("offset", 0))
    width = int(item.get("width_bytes", 1))
    if width <= 0 or offset < 0 or offset + width > len(data):
        raise FormulaError(f"Field {item.get('name')} exceeds response data ({offset}+{width}>{len(data)})")
    raw_bytes = data[offset:offset + width]
    endian = str(item.get("endian", "big"))
    raw = int.from_bytes(raw_bytes, endian, signed=False)
    signed = int.from_bytes(raw_bytes, endian, signed=True)
    formula = str(item.get("formula", "raw"))
    value = evaluate_formula(formula, _field_variables(data, raw, signed))
    bounds_status, expected_status = _quality(value, item, definition)
    return {
        "name": str(item.get("name", "field")),
        "value": value,
        "unit": str(item.get("unit", "")),
        "raw_hex": raw_bytes.hex().upper(),
        "formula": formula,
        "evidence_grade": str(item.get("evidence_grade", definition.get("evidence_grade", "CANDIDATE"))),
        "semantic_status": str(item.get("semantic_status", "")),
        "bounds_status": bounds_status,
        "expected_status": expected_status,
        "ocr_labels": list(item.get("ocr_labels", [])),
        "ocr_tolerance": item.get("ocr_tolerance"),
    }


def _decode_repeat(data: bytes, repeat: dict[str, Any], definition: dict[str, Any],
                   *, decoder: str) -> list[dict[str, Any]]:
    count = int(repeat.get("count", 0))
    width = int(repeat.get("width_bytes", 0))
    if decoder == "block_array":
        start = int(repeat.get("data_offset", definition.get("preamble_bytes", 0)))
        raw_offset = float(repeat.get("offset", 0.0))
    else:
        start = int(repeat.get("offset", 0))
        raw_offset = float(repeat.get("raw_offset", 0.0))
    if count <= 0 or width <= 0 or start < 0 or start + count * width > len(data):
        raise FormulaError(f"Repeat layout exceeds response data ({start}+{count}*{width}>{len(data)})")
    endian = str(repeat.get("endian", "big"))
    scale = float(repeat.get("scale", 1.0))
    formula = repeat.get("formula")
    rows: list[dict[str, Any]] = []
    for index in range(count):
        raw_bytes = data[start + index * width:start + (index + 1) * width]
        raw = int.from_bytes(raw_bytes, endian, signed=False)
        signed = int.from_bytes(raw_bytes, endian, signed=True)
        value = evaluate_formula(str(formula), _field_variables(data, raw, signed)) \
            if formula else (raw + raw_offset) * scale
        bounds_status, expected_status = _quality(
            value, repeat, definition, inherit_definition_bounds=True)
        label_pattern = repeat.get("ocr_label_pattern")
        labels = [str(label_pattern).format(index=index + 1)] if label_pattern else []
        rows.append({
            "name": str(repeat.get("name", "value")),
            "index": index + 1,
            "value": value,
            "unit": str(repeat.get("unit", "")),
            "raw_hex": raw_bytes.hex().upper(),
            "formula": str(formula or f"(raw+{raw_offset})*{scale}"),
            "evidence_grade": str(repeat.get("evidence_grade", definition.get("evidence_grade", "CANDIDATE"))),
            "bounds_status": bounds_status,
            "expected_status": expected_status,
            "ocr_labels": labels,
            "ocr_tolerance": repeat.get("ocr_tolerance"),
        })
    return rows


def mask_vin(value: str) -> str:
    cleaned = "".join(character for character in value.upper() if character.isalnum())
    return cleaned[:11] + "*" * max(0, len(cleaned) - 11)


def decode_definition(payload: bytes, definition: dict[str, Any]) -> dict[str, Any] | None:
    prefix = _prefix(definition)
    if prefix and not payload.startswith(prefix):
        return None
    data = payload[len(prefix):]
    decoder = str(definition.get("decoder", ""))
    result: dict[str, Any] = {
        "decoder": decoder,
        "fields": [],
        "arrays": [],
        "identity": {},
        "warnings": [],
        "matched": True,
    }
    signature = definition.get("signature", {})
    response_length = signature.get("response_length_bytes")
    if response_length is not None and len(payload) != int(response_length):
        result["warnings"].append(
            f"response_length={len(payload)} expected={int(response_length)}")

    try:
        if decoder in {"field_map", "block_health_array"}:
            result["fields"] = [decode_field(data, item, definition)
                                for item in definition.get("fields", [])]
        elif decoder == "block_array":
            result["fields"] = [decode_field(data, item, definition)
                                for item in definition.get("fields", [])]
        elif decoder == "ascii_model_signature":
            identity_bytes = data.split(b"\x00", 1)[0]
            text = "".join(chr(value) if 32 <= value <= 126 else " " for value in identity_bytes).strip()
            result["identity"] = {"text": " ".join(text.split())}
            required = str(signature.get("ascii_contains", ""))
            if required and required not in text:
                return None
        elif decoder == "response_signature":
            pass
        elif decoder == "ascii_field":
            spec = definition.get("ascii_field", {})
            start = int(spec.get("offset", 0))
            length = int(spec.get("length", len(data) - start))
            text = data[start:start + length].decode("ascii", errors="replace").strip("\x00 ")
            result["identity"] = {str(spec.get("name", "ascii_value")): text}
        elif decoder == "vin":
            start = int(definition.get("prefix_skip_bytes", 0))
            vin = data[start:].decode("ascii", errors="ignore").strip("\x00 ")
            result["identity"] = {"vin": vin, "vin_masked": mask_vin(vin)}

        if decoder in {"block_array", "block_health_array", "resistance_array"}:
            result["arrays"] = _decode_repeat(data, definition.get("repeat", {}), definition,
                                               decoder=decoder)

        values = {entry["name"]: entry["value"] for entry in result["fields"]}
        for item in definition.get("derived_fields", []):
            value = evaluate_formula(str(item["formula"]), values)
            bounds_status, expected_status = _quality(value, item, definition)
            result["fields"].append({
                "name": str(item["name"]), "value": value,
                "unit": str(item.get("unit", "")), "raw_hex": "",
                "formula": str(item["formula"]),
                "evidence_grade": str(item.get("evidence_grade", definition.get("evidence_grade", "CANDIDATE"))),
                "semantic_status": "DERIVED", "bounds_status": bounds_status,
                "expected_status": expected_status, "ocr_labels": list(item.get("ocr_labels", [])),
                "ocr_tolerance": item.get("ocr_tolerance"),
            })
    except FormulaError as error:
        result["warnings"].append(str(error))
        result["matched"] = False
    return result


def decoded_summary(decoded: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in decoded.get("fields", [])[:8]:
        value = item.get("value")
        rendered = f"{value:.6g}" if isinstance(value, float) else str(value)
        parts.append(f"{item.get('name')}={rendered}{item.get('unit', '')}")
    arrays = decoded.get("arrays", [])
    if arrays:
        values = [float(item["value"]) for item in arrays]
        parts.append(f"{arrays[0]['name']}_count={len(values)}")
        parts.append(f"min={min(values):.6g}{arrays[0].get('unit', '')}")
        parts.append(f"max={max(values):.6g}{arrays[0].get('unit', '')}")
    identity = decoded.get("identity", {})
    if identity:
        parts.extend(f"{key}={value}" for key, value in identity.items() if key != "vin")
    return ";".join(parts)
