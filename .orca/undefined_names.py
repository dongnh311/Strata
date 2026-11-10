"""Flag calls to names that are bound nowhere in the module (the mcp_note class of merge loss)."""
import ast, builtins, sys
from pathlib import Path

BOUND_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom,
               ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith,
               ast.comprehension, ast.ExceptHandler, ast.Global, ast.Nonlocal, ast.Lambda, ast.arguments)


def bound_names(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = node.args
                for arg in list(a.args) + list(a.posonlyargs) + list(a.kwonlyargs) + [a.vararg, a.kwarg]:
                    if arg is not None:
                        out.add(arg.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for al in node.names:
                out.add((al.asname or al.name).split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            out.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
    return out


def main(paths):
    bad = 0
    files = []
    for p in paths:
        q = Path(p)
        if q.is_dir():
            files += sorted(str(f) for f in q.glob("*.py"))
        else:
            files += sorted(str(f) for f in q.parent.glob(q.name)) if any(c in p for c in "*?[") else [p]
    for p in files:
        src = Path(p).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=p)
        have = bound_names(tree) | set(dir(builtins)) | {"__name__", "__file__", "self", "cls"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id not in have:
                    print(f"{p}:{node.lineno}: calls undefined name {node.func.id!r}")
                    bad += 1
    print(f"\n{bad} suspicious call(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
