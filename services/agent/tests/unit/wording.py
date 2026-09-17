"""Finds wording in Python source: the check behind "all wording lives in `src/prompts`".

A string is wording when it is not a docstring, a pydantic `Field(description=...)` (tool
schemas the model reads beside the tool) or SQL in `db/queries/`, and either
- reads as text: at least `MIN_CHARS` long with a space, or over several lines, or
- is handed to something that shows it: `emit.progress`/`emit.notice`, an error constructor
  (`...Error`, `HTTPException`, `RoleDidNotSubmit` and other `AgentError`s) or a `message=` or
  `detail=` argument, and has a word in it.
Parts of an f-string count one by one, so `f"The court could not answer: {x}."` is caught.
"""

import ast
import re

MIN_CHARS = 12
SHOWN_CALLS = {"progress", "notice", "HTTPException", "RoleDidNotSubmit", "PersonaInvalid"}
SHOWN_KEYWORDS = {"message", "detail"}
SQL = re.compile(r"\s*(SELECT|INSERT|UPDATE|DELETE|WITH)\b")
WORD = re.compile(r"[A-Za-z]{2,}.* |.* [A-Za-z]{2,}")


def _name(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _strings(node: ast.AST) -> list[ast.Constant]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _skipped(tree: ast.AST) -> set[int]:
    skipped = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.body and isinstance(node.body[0], ast.Expr):
                skipped.add(id(node.body[0].value))
        if isinstance(node, ast.Call) and _name(node.func) == "Field":
            for keyword in node.keywords:
                if keyword.arg == "description":
                    skipped.update(id(s) for s in _strings(keyword.value))
    return skipped


def _shown(tree: ast.AST) -> set[int]:
    shown = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _name(node.func)
        if name in SHOWN_CALLS or name.endswith("Error"):
            for arg in node.args:
                shown.update(id(s) for s in _strings(arg))
        for keyword in node.keywords:
            if keyword.arg in SHOWN_KEYWORDS:
                shown.update(id(s) for s in _strings(keyword.value))
    return shown


def _symbol(tree: ast.Module, line: int) -> str:
    """The top-level def, class or assigned name the line belongs to."""
    for node in tree.body:
        if node.lineno <= line <= (node.end_lineno or node.lineno):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                return node.name
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                return node.targets[0].id
    return ""


def wording(source: str, sql: bool = False) -> list[tuple[int, str, str]]:
    """Each piece of wording: its line, its top-level symbol and the text. `sql`: the source is
    a query module, whose SQL statements are not wording."""
    tree = ast.parse(source)
    skipped, shown = _skipped(tree), _shown(tree)
    found = []
    for node in _strings(tree):
        text = node.value
        if id(node) in skipped or (sql and SQL.match(text)):
            continue
        reads = (len(text) >= MIN_CHARS and " " in text) or "\n" in text.strip()
        if reads or (id(node) in shown and WORD.search(text)):
            found.append((node.lineno, _symbol(tree, node.lineno), text))
    return sorted(found)
