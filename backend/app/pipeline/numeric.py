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
    s = re.sub(r"(?:₹|\bRs\.?|\bINR)\s*", "", s)  # rupee markers
    s = re.sub(r"(?<=\d),(?=(?:\d{2},)*\d{3}(?!\d))", "", s)  # 8,628.79 and Indian grouping 1,23,456.50
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


# ---------------------------------------------------------------------------
# Formula-level check for interest problems
# ---------------------------------------------------------------------------
# `check_text` only sees one line where BOTH sides of "=" are numbers. A worked
# problem usually spreads over several lines ("P = 8500, r = 0.003, t = 5" ...
# "Final Answer: £8,628.79"), so the inputs are never on the same line as the
# answer. This check reads a whole problem, collects its variable bindings,
# recomputes simple and compound results in Python, and flags stated money
# results that match none of them.

_BINDING = re.compile(r"(?<![A-Za-z])([Prtn])\s*=\s*((?:\d[\d,]*(?:\.\d+)?\s*%?\s*=\s*)*\d[\d,]*(?:\.\d+)?\s*%?)(?!\s*[×*·x(\^\d])")
_PROBLEM_START = re.compile(r"^\s*(#{2,4}\s|\*\*(?:problem|example|task|exercise)|(?:problem|example|task|question|q)\s*\d)", re.I)
_CURRENCY = r"(?:[£$€₹]|\bRs\.?|\bINR)"
_RESULT_LINE = re.compile(rf"final answer|answer|yields|results? in|gives|total|final value|=\s*{_CURRENCY}", re.I)
_MONEY = re.compile(rf"{_CURRENCY}\s?(\d[\d,]*(?:\.\d+)?)|=\s*(\d[\d,]*\.\d{{2}})\b")


def _to_number(raw: str) -> float:
    last = re.split(r"\s*=\s*", raw.strip())[-1]  # "0.3% = 0.003" -> "0.003"
    pct = last.endswith("%")
    value = float(last.rstrip("% ").replace(",", ""))
    return value / 100 if pct else value


@dataclass
class FormulaCheck:
    location: str
    bindings: dict[str, float]
    stated: float
    expected: dict[str, float]
    line: str

    @property
    def detail(self) -> str:
        p, r, t, n = (self.bindings.get(k) for k in ("P", "r", "t", "n"))
        compound = self.expected["compound amount"]
        return (f"With P={p:g}, r={r:g}, t={t:g}" + (f", n={n:g}" if n else "") +
                f": compound amount = {compound:,.2f} (interest {compound - p:,.2f}), "  # type: ignore[operator]
                f"simple amount = {self.expected['simple amount']:,.2f} "
                f"(interest {self.expected['simple interest']:,.2f}); the text states {self.stated:,.2f}")


def _expected(b: dict[str, float]) -> dict[str, float]:
    p, r, t = b["P"], b["r"], b["t"]
    n = b.get("n", 1.0) or 1.0
    compound = p * (1 + r / n) ** (n * t)
    return {"compound amount": compound, "compound interest": compound - p,
            "simple amount": p * (1 + r * t), "simple interest": p * r * t}


def check_problem_results(text: str, location: str) -> list[FormulaCheck]:
    """Flag stated money results of a worked problem that don't match its own P, r, t (and n)."""
    problems: list[FormulaCheck] = []
    bindings: dict[str, float] = {}
    for raw_line in text.splitlines():
        line = re.sub(r"\[S\d+(?:\s*[,;]\s*S\d+)*\]", " ", raw_line)
        if _PROBLEM_START.search(line):
            bindings = {}  # a new problem starts: forget the previous one's variables
        for name, raw in _BINDING.findall(line):
            try:
                bindings[name] = _to_number(raw)
            except ValueError:
                continue
        if not {"P", "r", "t"} <= bindings.keys() or not _RESULT_LINE.search(line):
            continue
        if not (0 < bindings["r"] < 1 and 0 < bindings["t"] <= 100 and bindings["P"] > 0):
            continue  # implausible bindings (e.g. r written as 5 not 0.05): don't guess
        expected = _expected(bindings)
        for match in _MONEY.finditer(line):
            stated = float((match.group(1) or match.group(2)).replace(",", ""))
            if abs(stated - bindings["P"]) < 0.005:
                continue  # restating the principal
            # Tolerance = one cent + the error from rounding the growth factor to 4 decimals (P × 0.00005).
            # (A relative 1e-4 tolerance was too loose: ±£0.86 on £8,628 let £8,628.79 pass for £8,628.27.)
            tolerance = 0.011 + bindings["P"] * 0.00005
            if any(abs(stated - v) <= tolerance for v in expected.values()):
                continue
            problems.append(FormulaCheck(location, dict(bindings), stated, expected, line.strip()))
    unique: dict[float, FormulaCheck] = {}
    for p in problems:
        unique.setdefault(round(p.stated, 2), p)  # one finding per wrong figure per block
    return list(unique.values())
