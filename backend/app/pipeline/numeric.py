"""Recompute every arithmetic equality written in a lesson (QC1, step 6 of the spec).

Finds chains like  "10000 \\cdot 1.157625 = \\$11,576.25"  or  "(1.0125)^{40} \\approx 1.643619"
(LaTeX or plain), evaluates each numeric side with a safe evaluator, and flags any
side that disagrees with the others beyond rounding.
"""

import ast
import operator
import re
from dataclasses import dataclass

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_eval(expr: str) -> float | None:
    """Evaluate + - * / ** and parentheses on numbers only. None if anything else appears."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsupported")

    try:
        return ev(tree)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def normalize(line: str) -> str:
    s = re.sub(r"\[S\d+(?:\s*[,;]\s*S\d+)*\]", " ", line)  # citations
    # Asides like "(approx)" or "(rounded to two decimal places)" must not break an equation chain.
    s = re.sub(r"\((?:approx\.?|approximately|rounded[^)]*|to \d+ decimal places?)\)", " ", s, flags=re.I)
    for _ in range(3):  # \frac{a}{b} → ((a)/(b)), innermost first
        s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", s)
    s = s.replace("\\left", "").replace("\\right", "")
    s = re.sub(r"\\(?:cdot|times)|[×·]", "*", s)
    s = s.replace("\\approx", "≈").replace("\\$", "").replace("$", "").replace("\\,", "").replace("**", "*")
    s = s.replace("^", "**").replace("{", "(").replace("}", ")")
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)  # thousands separators
    s = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", s)
    s = re.sub(r"(\d|\))\s*\(", r"\1*(", s)  # implicit multiplication: 10000 (1.05) / )(
    s = re.sub(r"\)\s*(\d)", r")*\1", s)
    s = s.replace("**(", "**(")
    return s


_NUM = r"\(?\s*-?\d+(?:\.\d+)?\s*\)?"
_EXPR = rf"(?:\(+\s*)*-?\d+(?:\.\d+)?(?:\s*\)+)*(?:\s*(?:\*\*|[-+*/])\s*(?:\(+\s*)*-?\d+(?:\.\d+)?(?:\s*\)+)*)*"
_CHAIN = re.compile(rf"({_EXPR})((?:\s*[=≈]\s*{_EXPR})+)")


def _decimals(literal: str) -> int:
    match = re.search(r"\.(\d+)\s*\)*\s*$", literal.strip())
    return len(match.group(1)) if match else 0


@dataclass
class NumericCheck:
    location: str
    expression: str
    values: list[float]
    ok: bool
    detail: str


def check_text(text: str, location: str) -> list[NumericCheck]:
    checks: list[NumericCheck] = []
    for raw_line in text.splitlines():
        line = normalize(raw_line)
        for match in _CHAIN.finditer(line):
            parts = re.split(r"\s*[=≈]\s*", match.group(0).strip())
            if len(parts) < 2 or not any(re.search(r"[\d)]\s*(?:\*\*|[-+*/])\s*[\d(]", p) for p in parts):
                continue  # no arithmetic to check (e.g. "n = 1")
            if any(p.count("(") != p.count(")") for p in parts):
                continue
            values = [safe_eval(p) for p in parts]
            if any(v is None for v in values):
                continue
            approx = "≈" in match.group(0)
            reference = values[-1]
            ok = True
            worst = ""
            for part, value in zip(parts[:-1], values[:-1]):
                decimals = max(_decimals(parts[-1]), 0)
                tol = max(0.5 * 10 ** -decimals * 1.01, abs(reference) * (0.005 if approx else 1e-4), 1e-9)
                if abs(value - reference) > tol:  # type: ignore[operator]
                    ok = False
                    worst = f"{part.strip()} = {value:,.6g}, but the text says {parts[-1].strip()}"
            checks.append(NumericCheck(location=location, expression=match.group(0).strip(),
                                       values=[round(v, 6) for v in values],  # type: ignore[arg-type]
                                       ok=ok, detail=worst or "matches"))
    return checks
