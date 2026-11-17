"""Small AST mutation engine: one mutant per mutation site."""

from __future__ import annotations

import ast
import copy
import random

_CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
             ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
             ast.Is: ast.IsNot, ast.IsNot: ast.Is}
_BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
             ast.Div: ast.Mult, ast.Mod: ast.FloorDiv, ast.Pow: ast.Mult}


def _sites(tree: ast.AST) -> list[tuple[int, str]]:
    sites = []
    for i, node in enumerate(ast.walk(tree)):
        if isinstance(node, ast.Compare) and type(node.ops[0]) in _CMP_SWAP:
            sites.append((i, "cmp"))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BIN_SWAP:
            sites.append((i, "bin"))
        elif isinstance(node, ast.BoolOp):
            sites.append((i, "bool"))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append((i, "not"))
        elif isinstance(node, ast.Constant) and type(node.value) in (int, bool):
            sites.append((i, "const"))
        elif isinstance(node, ast.Return) and node.value is not None:
            sites.append((i, "return"))
    return sites


class _Apply(ast.NodeTransformer):
    def __init__(self, target: int, kind: str, index: dict):
        self.target, self.kind, self.index = target, kind, index

    def generic_visit(self, node):
        if self.index.get(id(node)) == self.target:
            return self._mutate(node)
        return super().generic_visit(node)

    def _mutate(self, node):
        k = self.kind
        if k == "cmp":
            node.ops[0] = _CMP_SWAP[type(node.ops[0])]()
        elif k == "bin":
            node.op = _BIN_SWAP[type(node.op)]()
        elif k == "bool":
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        elif k == "not":
            return node.operand
        elif k == "const":
            node.value = (not node.value) if isinstance(node.value, bool) else node.value + 1
        elif k == "return":
            node.value = ast.Constant(None)
        return node


def mutants(source: str, limit: int = 30, seed: int = 0) -> list[str]:
    tree = ast.parse(source)
    sites = _sites(tree)
    random.Random(seed).shuffle(sites)
    out = []
    for target, kind in sites[:limit]:
        t = copy.deepcopy(tree)
        index = {id(n): i for i, n in enumerate(ast.walk(t))}
        mutated = ast.fix_missing_locations(_Apply(target, kind, index).visit(t))
        try:
            src = ast.unparse(mutated)
        except Exception:
            continue
        if src != ast.unparse(tree):
            out.append(src)
    return out
