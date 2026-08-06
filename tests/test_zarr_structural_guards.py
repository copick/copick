"""AST guards for the Zarr v2 hardening phase."""

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
ZARR_ENTRY_POINTS = {
    "open",
    "open_group",
    "open_array",
    "group",
    "create",
    "array",
    "create_group",
    "create_array",
}
ZARR_OPEN_ENTRY_POINTS = {"open", "open_group", "open_array"}
ZARR_CREATION_MODES = {"a", "w", "w-", "x"}

# These tests intentionally assert copick's canonical numeric writer output.
# Every entry must correspond to a violation observed by the repository scan,
# which prevents stale or overly broad exemptions.
ALLOWED_VIOLATIONS = {
    ("tests/test_ome_writer.py", "test_writer_preserves_v2_golden_contract", "metadata_level_path"),
    ("tests/test_ome_writer.py", "test_writer_preserves_default_chunk_shape", "metadata_level_path"),
    ("tests/test_ome_writer.py", "test_zarr_handler_uses_canonical_writer_contract", "metadata_level_path"),
}


@dataclass(frozen=True)
class Violation:
    path: str
    scope: str
    line: int
    rule: str
    message: str

    @property
    def allowlist_key(self):
        return self.path, self.scope, self.rule

    def __str__(self):
        return f"{self.path}:{self.line} ({self.scope}) [{self.rule}] {self.message}"


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix:
            return f"{prefix}.{node.attr}"
    return None


def _constant_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_constant(node, value):
    return isinstance(node, ast.Constant) and node.value == value


class ZarrStructuralGuard(ast.NodeVisitor):
    """Find structural migration-policy violations in one Python module."""

    def __init__(self, path):
        self.path = path
        self.scope = ["<module>"]
        self.module_aliases = {}
        self.function_aliases = {}
        self.zarr_group_names = set()
        self.array_listing_names = set()
        self.violations = []

    def _add(self, node, rule, message):
        self.violations.append(Violation(self.path, self.scope[-1], node.lineno, rule, message))

    def _canonical_call_name(self, call):
        raw_name = _dotted_name(call.func)
        if raw_name is None:
            return None
        if raw_name in self.function_aliases:
            return self.function_aliases[raw_name]

        head, separator, tail = raw_name.partition(".")
        if head in self.module_aliases:
            canonical = self.module_aliases[head]
            return f"{canonical}.{tail}" if separator else canonical
        return raw_name

    @staticmethod
    def _keyword(call, name):
        return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)

    def _mode(self, call):
        keyword_mode = self._keyword(call, "mode")
        if keyword_mode is not None:
            return keyword_mode
        return call.args[1] if len(call.args) > 1 else None

    def _has_v2_format(self, call):
        return _is_constant(self._keyword(call, "zarr_version"), 2)

    def _is_zarr_group_expression(self, node):
        if isinstance(node, ast.Name):
            return node.id in self.zarr_group_names or node.id == "group" or node.id.endswith("_group")
        if isinstance(node, ast.Attribute):
            return node.attr == "group" or node.attr.endswith("_group")
        if isinstance(node, ast.Call):
            name = self._canonical_call_name(node)
            return name in {f"zarr.{entry}" for entry in ZARR_OPEN_ENTRY_POINTS | {"group"}}
        return False

    @staticmethod
    def _is_array_listing(node):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "list":
            return False
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Call):
            return False
        return isinstance(node.args[0].func, ast.Attribute) and node.args[0].func.attr == "arrays"

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name == "zarr" or alias.name == "ome_zarr.writer":
                if alias.asname:
                    self.module_aliases[alias.asname] = alias.name
                else:
                    self.module_aliases[alias.name.split(".")[0]] = alias.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in {"zarr", "ome_zarr.writer"}:
            for alias in node.names:
                local_name = alias.asname or alias.name
                self.function_aliases[local_name] = f"{node.module}.{alias.name}"
        elif node.module == "ome_zarr":
            for alias in node.names:
                if alias.name == "writer":
                    self.module_aliases[alias.asname or alias.name] = "ome_zarr.writer"
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Call):
            call_name = self._canonical_call_name(node.value)
            if call_name in {f"zarr.{entry}" for entry in ZARR_OPEN_ENTRY_POINTS | {"group"}}:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.zarr_group_names.add(target.id)
        if self._is_array_listing(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.array_listing_names.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node):
        call_name = self._canonical_call_name(node)
        if call_name and call_name.startswith("zarr."):
            entry_point = call_name.removeprefix("zarr.")
            if entry_point in ZARR_ENTRY_POINTS:
                mode_node = self._mode(node) if entry_point in ZARR_OPEN_ENTRY_POINTS else None
                mode = _constant_string(mode_node)

                if entry_point in ZARR_OPEN_ENTRY_POINTS and mode_node is None:
                    self._add(node, "explicit_open_mode", f"zarr.{entry_point} requires an explicit mode")

                creates = entry_point not in ZARR_OPEN_ENTRY_POINTS or mode_node is None or mode in ZARR_CREATION_MODES
                if creates and not self._has_v2_format(node):
                    self._add(
                        node,
                        "explicit_zarr_format",
                        f"creation through zarr.{entry_point} requires zarr_version=2",
                    )

        if call_name == "ome_zarr.writer.write_multiscale" and self._keyword(node, "fmt") is None:
            self._add(
                node,
                "explicit_write_multiscale_format",
                "write_multiscale requires an explicit fmt keyword",
            )

        self.generic_visit(node)

    def visit_Subscript(self, node):
        if not isinstance(node.ctx, ast.Load):
            self.generic_visit(node)
            return

        if _is_constant(node.slice, "0") and self._is_zarr_group_expression(node.value):
            self._add(node, "metadata_level_path", 'read a level through metadata instead of literal path "0"')

        if (
            isinstance(node.slice, ast.Call)
            and isinstance(node.slice.func, ast.Name)
            and node.slice.func.id == "str"
            and len(node.slice.args) == 1
            and isinstance(node.slice.args[0], ast.Name)
            and "level" in node.slice.args[0].id
        ):
            self._add(node, "metadata_level_path", "read a level through metadata instead of str(level)")

        reads_first_array = _is_constant(node.slice, 0) and (
            self._is_array_listing(node.value)
            or isinstance(node.value, ast.Name)
            and node.value.id in self.array_listing_names
        )
        if reads_first_array:
            self._add(node, "metadata_level_path", "do not select a level using Group.arrays() iteration order")

        self.generic_visit(node)


def find_violations(source, path="<fixture>"):
    guard = ZarrStructuralGuard(path)
    guard.visit(ast.parse(source))
    return guard.violations


def _repository_python_files():
    roots = (PROJECT_ROOT / "src" / "copick", PROJECT_ROOT / "tests", PROJECT_ROOT / "docs" / "snippets")
    for root in roots:
        yield from root.rglob("*.py")


def test_repository_obeys_zarr_structural_guards():
    violations = []
    for source_path in _repository_python_files():
        relative_path = source_path.relative_to(PROJECT_ROOT).as_posix()
        violations.extend(find_violations(source_path.read_text(), relative_path))

    observed_allowlist = {violation.allowlist_key for violation in violations} & ALLOWED_VIOLATIONS
    assert observed_allowlist == ALLOWED_VIOLATIONS, "Structural-guard allow-list contains stale entries"

    unexpected = [violation for violation in violations if violation.allowlist_key not in ALLOWED_VIOLATIONS]
    assert not unexpected, "Unexpected Zarr structural violations:\n" + "\n".join(map(str, unexpected))


@pytest.mark.parametrize("entry_point", sorted(ZARR_ENTRY_POINTS))
def test_guard_rejects_creation_without_explicit_v2_format(entry_point):
    arguments = "store, mode='w'" if entry_point in ZARR_OPEN_ENTRY_POINTS else "data"
    violations = find_violations(f"import zarr\nzarr.{entry_point}({arguments})\n")

    assert "explicit_zarr_format" in {violation.rule for violation in violations}


def test_guard_rejects_wrong_creation_format():
    violations = find_violations("import zarr\nzarr.group(store, zarr_version=3)\n")

    assert "explicit_zarr_format" in {violation.rule for violation in violations}


@pytest.mark.parametrize("entry_point", sorted(ZARR_OPEN_ENTRY_POINTS))
def test_guard_rejects_open_without_explicit_mode(entry_point):
    violations = find_violations(f"import zarr\nzarr.{entry_point}(store, zarr_version=2)\n")

    assert "explicit_open_mode" in {violation.rule for violation in violations}


def test_guard_rejects_write_multiscale_without_explicit_format():
    source = "from ome_zarr.writer import write_multiscale\nwrite_multiscale(images, group=group)\n"

    assert "explicit_write_multiscale_format" in {violation.rule for violation in find_violations(source)}


@pytest.mark.parametrize(
    "statement",
    [
        'array = group["0"]',
        "array = group[str(level)]",
        "array = list(group.arrays())[0]",
        "arrays = list(group.arrays())\narray = arrays[0]",
    ],
)
def test_guard_rejects_level_reads_that_bypass_metadata(statement):
    violations = find_violations(f"def read(group, level):\n    {statement.replace(chr(10), chr(10) + '    ')}\n")

    assert "metadata_level_path" in {violation.rule for violation in violations}


def test_guard_accepts_explicit_v2_creation_and_metadata_level_resolution():
    source = """
import zarr
from ome_zarr.writer import write_multiscale

zarr.open(store, mode="w", zarr_version=2)
zarr.open_group(store, mode="w", zarr_version=2)
zarr.open_array(store, mode="w", zarr_version=2)
zarr.group(store, zarr_version=2)
zarr.create(shape, zarr_version=2)
zarr.array(data, zarr_version=2)
zarr.create_group(store, zarr_version=2)
zarr.create_array(store, zarr_version=2)
write_multiscale(images, group=group, fmt=fmt)
array = group[get_level_path(group, level)]
"""

    assert find_violations(source) == []


def test_guard_resolves_import_aliases():
    source = """
import zarr as zr
from ome_zarr.writer import write_multiscale as write
from zarr import open as zopen

zr.create(shape)
zopen(store)
write(images, group=group)
"""

    assert {violation.rule for violation in find_violations(source)} == {
        "explicit_open_mode",
        "explicit_write_multiscale_format",
        "explicit_zarr_format",
    }


def test_guard_resolves_dotted_writer_import():
    source = "import ome_zarr.writer\nome_zarr.writer.write_multiscale(images, group=group)\n"

    assert "explicit_write_multiscale_format" in {violation.rule for violation in find_violations(source)}
