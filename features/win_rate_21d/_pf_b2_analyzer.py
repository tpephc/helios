# features/win_rate_21d/_pf_b2_analyzer.py
"""PF-B2 canonical-source AST analyzer — v1.5.0. Dual-layer structural verification.

Private module implementing the dual-layer structural verification for
PF-B2 (D-PR2C-3 mechanism, D-PR2C-10 predicate semantics and guarantee
boundary).  Consumed exclusively by ``pf_b2_canonical_source_check`` in
``pre_flight.py``.

Governed inspection target: ``features.win_rate_21d.compute`` (only).
This module is part of the pre-flight subsystem and is NOT itself a
PF-B2 governed target (D-PR2C-10 §10 addressee asymmetry).

Layer-2 supported-pattern whitelist (D-PR2C-10 §5):

    P-1  Canonical binding provenance (load-bearing).
    P-2  Single-hop local assignment (direct ``func.body`` statement only).
    P-3  Governed sink.

Everything outside this whitelist fails closed (D-PR2C-10 §6).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from string import Formatter
from typing import Final

__all__ = [
    "FORBIDDEN_SOURCE_LITERAL",
    "GOVERNED_IMPORT_MODULE",
    "GOVERNED_MODULE",
    "GOVERNED_NAME",
    "SUPPORTED_TEMPLATE_FIELD",
    "SUPPORTED_TEMPLATE_NAME",
    "AnalysisResult",
    "AnalysisVerdict",
    "analyze_source",
]


# ---------------------------------------------------------------------------
# Governance constants (D-PR2C-10 §10)
# ---------------------------------------------------------------------------

GOVERNED_MODULE: Final[str] = "features.win_rate_21d.compute"
GOVERNED_NAME: Final[str] = "CANONICAL_PIT_VIEW_NAME"
FORBIDDEN_SOURCE_LITERAL: Final[str] = "daily_price_adj"
GOVERNED_IMPORT_MODULE: Final[str] = "features.win_rate_21d.constants"
SUPPORTED_TEMPLATE_NAME: Final[str] = "_SQL_MEDIAN_QUERY_TEMPLATE"
SUPPORTED_TEMPLATE_FIELD: Final[str] = "view_name"
"""The ``.format()`` keyword through which the governed name must enter
the template.  Verified against HEAD ``compute.py`` line 86.  The
analyzer verifies BOTH that the template string contains
``{view_name}`` AND that the ``.format()`` call passes
``view_name=CANONICAL_PIT_VIEW_NAME``.  P-2 narrowing (§7).
"""


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class AnalysisVerdict(Enum):
    """Outcome classification for the dual-layer analysis."""

    PASS = "pass"
    LAYER1_VIOLATION = "layer1_violation"
    LAYER2_VIOLATION = "layer2_violation"


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Immutable outcome of ``analyze_source``."""

    verdict: AnalysisVerdict
    diagnostics: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """``True`` iff both layers passed."""
        return self.verdict is AnalysisVerdict.PASS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_source(
    source: str,
    *,
    source_identity: str,
) -> AnalysisResult:
    """Run the dual-layer PF-B2 analysis on raw source text.

    Raises:
        SyntaxError: if ``source`` cannot be parsed (infrastructure failure).
    """
    tree = ast.parse(source)

    layer1 = _check_layer1(tree, source_identity)
    if layer1:
        return AnalysisResult(verdict=AnalysisVerdict.LAYER1_VIOLATION, diagnostics=tuple(layer1))

    layer2 = _check_layer2(tree)
    if layer2:
        return AnalysisResult(verdict=AnalysisVerdict.LAYER2_VIOLATION, diagnostics=tuple(layer2))

    return AnalysisResult(verdict=AnalysisVerdict.PASS, diagnostics=())


# ---------------------------------------------------------------------------
# Layer 1 — forbidden literal detection
# ---------------------------------------------------------------------------


def _check_layer1(tree: ast.Module, source_identity: str) -> list[str]:
    """Exact-equality forbidden-literal scan (D-PR2C-10 §2)."""
    violations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == FORBIDDEN_SOURCE_LITERAL
        ):
            violations.append(
                f'forbidden raw-table literal "{FORBIDDEN_SOURCE_LITERAL}" '
                f"detected at {source_identity}:{node.lineno}"
            )
    return violations


# ---------------------------------------------------------------------------
# Layer 2 — canonical identifier binding chain
# ---------------------------------------------------------------------------


def _check_layer2(tree: ast.Module) -> list[str]:
    """Orchestrate P-1, template provenance, P-2, P-3."""
    issue = _check_governed_name_provenance(tree)
    if issue is not None:
        return [issue]

    issue = _check_template_provenance(tree)
    if issue is not None:
        return [issue]

    if not _has_governed_chain(tree):
        return [
            f"{GOVERNED_NAME} not reachable to DuckDB execution sink "
            "via resolvable local assignment chain"
        ]
    return []


# ---- P-1: governed-name provenance ----------------------------------------


def _check_governed_name_provenance(tree: ast.Module) -> str | None:
    """P-1: exactly one canonical absolute ``ImportFrom``, no rebinding."""
    allowed: list[tuple[ast.ImportFrom, ast.alias]] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.ImportFrom):
            continue
        if stmt.module != GOVERNED_IMPORT_MODULE or stmt.level != 0:
            continue
        for alias in stmt.names:
            if alias.name == GOVERNED_NAME and alias.asname is None:
                allowed.append((stmt, alias))

    if len(allowed) == 0:
        return (
            f"{GOVERNED_NAME} has no qualifying ImportFrom binding at "
            f"module scope (required: absolute from {GOVERNED_IMPORT_MODULE} "
            f"import {GOVERNED_NAME}, no alias)"
        )
    if len(allowed) > 1:
        return (
            f"{GOVERNED_NAME} has {len(allowed)} qualifying ImportFrom "
            "bindings at module scope (expected exactly 1)"
        )

    allowed_node, allowed_alias = allowed[0]
    issues = _find_governed_name_rebindings(tree, allowed_node, allowed_alias)
    if issues:
        return f"{GOVERNED_NAME} has prohibited rebinding: {'; '.join(issues)}"
    return None


def _find_governed_name_rebindings(
    tree: ast.Module,
    allowed_node: ast.ImportFrom,
    allowed_alias: ast.alias,
) -> list[str]:
    """Full-module scan for any binding of ``GOVERNED_NAME``
    besides the allowed alias."""
    issues: list[str] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id == GOVERNED_NAME
            and isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            kind = "del" if isinstance(node.ctx, ast.Del) else "assignment"
            issues.append(f"{kind} at line {node.lineno}")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == GOVERNED_NAME:
                issues.append(f"function definition at line {node.lineno}")
            _check_governed_params(node.args, issues)

        elif isinstance(node, ast.ClassDef) and node.name == GOVERNED_NAME:
            issues.append(f"class definition at line {node.lineno}")

        elif isinstance(node, ast.Lambda):
            _check_governed_params(node.args, issues)

        elif isinstance(node, ast.ExceptHandler) and node.name == GOVERNED_NAME:
            issues.append(f"except-as binding at line {node.lineno}")

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname if alias.asname is not None else alias.name
                if bound != GOVERNED_NAME:
                    continue
                if node is allowed_node and alias is allowed_alias:
                    continue
                issues.append(f"import rebinding at line {node.lineno}")

        elif isinstance(node, ast.Global) and GOVERNED_NAME in node.names:
            issues.append(f"global declaration at line {node.lineno}")
        elif isinstance(node, ast.Nonlocal) and GOVERNED_NAME in node.names:
            issues.append(f"nonlocal declaration at line {node.lineno}")

    return issues


def _check_governed_params(args: ast.arguments, issues: list[str]) -> None:
    """Append to *issues* if any parameter binds ``GOVERNED_NAME``."""
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        if arg.arg == GOVERNED_NAME:
            issues.append(f"parameter at line {arg.lineno}")
    if args.vararg is not None and args.vararg.arg == GOVERNED_NAME:
        issues.append(f"*args parameter at line {args.vararg.lineno}")
    if args.kwarg is not None and args.kwarg.arg == GOVERNED_NAME:
        issues.append(f"**kwargs parameter at line {args.kwarg.lineno}")


# ---- Template provenance (P-2 narrowing, §7) -----------------------------


def _check_template_provenance(tree: ast.Module) -> str | None:
    """Verify the supported template has a unique string-constant
    assignment and no rebinding anywhere in the module.

    Architecture mirrors ``_check_governed_name_provenance``: identify
    the one allowed binding, then full-module ``ast.walk`` scan for
    anything else.
    """
    # Step 1: find qualifying module-scope Assign([Name], Constant[str]).
    # Must be single-target (len(targets)==1), same constraint as P-2.
    allowed_targets: list[tuple[ast.Assign, ast.Name]] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        # Check if any target in this statement binds the template name.
        has_template_target = any(
            isinstance(t, ast.Name) and t.id == SUPPORTED_TEMPLATE_NAME for t in stmt.targets
        )
        if not has_template_target:
            continue
        # Reject chained assignment (multi-target).
        if len(stmt.targets) != 1:
            return (
                f"{SUPPORTED_TEMPLATE_NAME} must use a single-target "
                f"module-scope assignment (line {stmt.lineno})"
            )
        target_node = stmt.targets[0]
        assert isinstance(target_node, ast.Name)  # guaranteed by has_template_target + len==1
        if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            allowed_targets.append((stmt, target_node))
        else:
            return (
                f"{SUPPORTED_TEMPLATE_NAME} module-scope assignment "
                f"is not a string constant (line {stmt.lineno})"
            )

    if len(allowed_targets) == 0:
        return f"{SUPPORTED_TEMPLATE_NAME} has no string-constant assignment at module scope"
    if len(allowed_targets) > 1:
        return (
            f"{SUPPORTED_TEMPLATE_NAME} has {len(allowed_targets)} "
            "qualifying assignments at module scope (expected exactly 1)"
        )

    allowed_stmt, allowed_name_node = allowed_targets[0]

    # Step 1b: verify the template string references the governed field.
    assert isinstance(allowed_stmt.value, ast.Constant)  # guaranteed above
    template_value = allowed_stmt.value.value
    assert isinstance(template_value, str)  # guaranteed above
    if not _template_references_field(template_value, SUPPORTED_TEMPLATE_FIELD):
        return (
            f"{SUPPORTED_TEMPLATE_NAME} does not reference "
            f"format field '{SUPPORTED_TEMPLATE_FIELD}' "
            f"(line {allowed_stmt.lineno})"
        )

    # Step 2: full-module binding scan.
    issues = _find_template_rebindings(tree, allowed_name_node)
    if issues:
        return f"{SUPPORTED_TEMPLATE_NAME} has prohibited rebinding: {'; '.join(issues)}"
    return None


def _find_template_rebindings(
    tree: ast.Module,
    allowed_target: ast.Name,
) -> list[str]:
    """Full-module scan for any binding of ``SUPPORTED_TEMPLATE_NAME``
    besides the allowed assignment target.

    Covers every binding form reachable via ``ast.walk``: assignments
    (including inside ``if``/``for``/``try``/``with``/``match`` at any
    scope), deletions, function/class definitions, except-as, imports,
    and ``global``/``nonlocal`` declarations.

    Function parameters are NOT checked here — function-local shadowing
    is handled by ``_count_local_bindings`` in ``_function_has_chain``.
    """
    issues: list[str] = []

    for node in ast.walk(tree):
        # Name(Store/Del) — the one allowed target is exempted.
        if (
            isinstance(node, ast.Name)
            and node.id == SUPPORTED_TEMPLATE_NAME
            and isinstance(node.ctx, (ast.Store, ast.Del))
        ):
            if node is allowed_target:
                continue
            kind = "del" if isinstance(node.ctx, ast.Del) else "assignment"
            issues.append(f"{kind} at line {node.lineno}")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == SUPPORTED_TEMPLATE_NAME:
                issues.append(f"function definition at line {node.lineno}")

        elif isinstance(node, ast.ClassDef) and node.name == SUPPORTED_TEMPLATE_NAME:
            issues.append(f"class definition at line {node.lineno}")

        elif isinstance(node, ast.ExceptHandler) and node.name == SUPPORTED_TEMPLATE_NAME:
            issues.append(f"except-as binding at line {node.lineno}")

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname if alias.asname is not None else alias.name
                if bound == SUPPORTED_TEMPLATE_NAME:
                    issues.append(f"import rebinding at line {node.lineno}")

        elif isinstance(node, ast.Global) and SUPPORTED_TEMPLATE_NAME in node.names:
            issues.append(f"global declaration at line {node.lineno}")
        elif isinstance(node, ast.Nonlocal) and SUPPORTED_TEMPLATE_NAME in node.names:
            issues.append(f"nonlocal declaration at line {node.lineno}")

    return issues


_FORMAT_PARSER: Final[Formatter] = Formatter()


def _template_references_field(template: str, field_name: str) -> bool:
    """Check if *template* contains a ``{field_name}`` format field.

    Uses ``string.Formatter.parse`` for robust field extraction
    (handles conversion, format spec, and escaped braces correctly).
    Returns ``False`` on malformed format strings (fail-closed).
    """
    try:
        return any(fname == field_name for _, fname, _, _ in _FORMAT_PARSER.parse(template))
    except (ValueError, KeyError):
        return False


# ---- P-2 + P-3: binding chain -------------------------------------------


def _has_governed_chain(tree: ast.Module) -> bool:
    """Check if any top-level function satisfies BOTH P-2 and P-3."""
    for stmt in tree.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _function_has_chain(stmt):
            return True
    return False


def _function_has_chain(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Check P-2 and P-3 within one function."""
    if _name_has_scope_declaration(func, GOVERNED_NAME):
        return False

    # Template must not be locally shadowed in this function.
    if _count_local_bindings(func, SUPPORTED_TEMPLATE_NAME) > 0:
        return False

    for stmt in func.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not _rhs_is_supported_format_call(stmt.value):
            continue

        var = target.id
        if _name_has_scope_declaration(func, var):
            continue
        if _count_local_bindings(func, var) != 1:
            continue
        if _var_reaches_execute_sink(func, var):
            return True

    return False


def _rhs_is_supported_format_call(value: ast.expr) -> bool:
    """Check if RHS is ``_SQL_MEDIAN_QUERY_TEMPLATE.format(...)``
    with governed Name as the value of the ``view_name`` keyword.

    The governed Name must enter the template through the specific
    keyword that the template actually references.  Positional
    governed arguments are not accepted (HEAD uses keyword form).

    Rejects starred positional args, ``**kwargs`` splat, arbitrary
    callables, unrecognized receivers, containers, lambdas, f-strings.
    """
    if not isinstance(value, ast.Call):
        return False
    if not isinstance(value.func, ast.Attribute):
        return False
    if value.func.attr != "format":
        return False
    if not isinstance(value.func.value, ast.Name):
        return False
    if value.func.value.id != SUPPORTED_TEMPLATE_NAME:
        return False

    if any(isinstance(arg, ast.Starred) for arg in value.args):
        return False
    if any(kw.arg is None for kw in value.keywords):
        return False

    # Governed Name must be the value of the specific template field keyword.
    return any(
        kw.arg == SUPPORTED_TEMPLATE_FIELD and _is_governed_name_load(kw.value)
        for kw in value.keywords
    )


def _is_governed_name_load(node: ast.expr) -> bool:
    """Check if *node* is exactly ``Name(id=GOVERNED_NAME, ctx=Load)``."""
    return (
        isinstance(node, ast.Name) and node.id == GOVERNED_NAME and isinstance(node.ctx, ast.Load)
    )


# ---------------------------------------------------------------------------
# Traversal helpers
# ---------------------------------------------------------------------------

_SCOPE_CREATORS: tuple[type[ast.AST], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _walk_function_scope(body: Sequence[ast.stmt]) -> Iterator[ast.AST]:
    """Yield nodes in a function body without crossing scope boundaries."""
    for stmt in body:
        yield from _walk_no_scope_cross(stmt)


def _walk_no_scope_cross(node: ast.AST) -> Iterator[ast.AST]:
    """Yield *node* and descendants, halting at scope boundaries."""
    yield node
    if isinstance(node, _SCOPE_CREATORS):
        return
    for child in ast.iter_child_nodes(node):
        yield from _walk_no_scope_cross(child)


def _name_has_scope_declaration(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
) -> bool:
    """Check for ``global`` or ``nonlocal`` declaration of *name*."""
    for node in _walk_function_scope(func.body):
        if isinstance(node, ast.Global) and name in node.names:
            return True
        if isinstance(node, ast.Nonlocal) and name in node.names:
            return True
    return False


def _is_local_binding(node: ast.AST, name: str) -> bool:
    """Check if *node* constitutes a binding (or unbinding) of *name*."""
    if (
        isinstance(node, ast.Name)
        and node.id == name
        and isinstance(node.ctx, (ast.Store, ast.Del))
    ):
        return True
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name == name
    if isinstance(node, ast.ExceptHandler):
        return node.name == name
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any(
            (alias.asname if alias.asname is not None else alias.name) == name
            for alias in node.names
        )
    return False


def _count_local_bindings(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
) -> int:
    """Count all binding sites for *name* in the function's local scope."""
    count = 0
    for arg in func.args.posonlyargs + func.args.args + func.args.kwonlyargs:
        if arg.arg == name:
            count += 1
    if func.args.vararg is not None and func.args.vararg.arg == name:
        count += 1
    if func.args.kwarg is not None and func.args.kwarg.arg == name:
        count += 1
    count += sum(1 for node in _walk_function_scope(func.body) if _is_local_binding(node, name))
    return count


def _var_reaches_execute_sink(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    var: str,
) -> bool:
    """P-3: *var* is a direct argument to ``.execute()``."""
    for node in _walk_function_scope(func.body):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "execute"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == var:
                return True
        for kw in node.keywords:
            if kw.arg is not None and isinstance(kw.value, ast.Name) and kw.value.id == var:
                return True
    return False
