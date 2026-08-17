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
ZARR_NON_CREATING_MODES = {"r", "r+"}
ZARR_CALL_ALIASES = {
    "zarr.convenience.open": "zarr.open",
    "zarr.hierarchy.open_group": "zarr.open_group",
}
REPOSITORY_SCAN_ROOTS = (PROJECT_ROOT / "src" / "copick", PROJECT_ROOT / "tests", PROJECT_ROOT / "docs" / "snippets")
REMOVED_ZARR_MODULE_PREFIXES = ("zarr.convenience", "zarr.hierarchy")
REMOVED_ZARR_SYMBOLS = {
    "zarr.copy_store",
    "zarr.core.Array",
    "zarr.storage.DirectoryStore",
    "zarr.storage.FSStore",
}
STORE_ARGUMENT_NAMES = {"loc", "source", "source_store", "store", "target", "target_store", "zarr_store"}

# These tests intentionally assert copick's canonical numeric writer output.
# Every entry must correspond to a violation observed by the repository scan,
# which prevents stale or overly broad exemptions.
ALLOWED_VIOLATIONS = {
    ("tests/test_ome_writer.py", "test_writer_emits_v3_ome_zarr_05_contract", "metadata_level_path"),
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
        self.array_listing_names = set()
        self.violations = []

    def _add(self, node, rule, message):
        self.violations.append(Violation(self.path, self.scope[-1], node.lineno, rule, message))

    def _canonical_call_name(self, call):
        raw_name = _dotted_name(call.func)
        if raw_name is None:
            return None
        head, separator, tail = raw_name.partition(".")
        canonical = self.function_aliases.get(head, self.module_aliases.get(head, head))
        resolved = f"{canonical}.{tail}" if separator else canonical
        return ZARR_CALL_ALIASES.get(resolved, resolved)

    def _canonical_name(self, node):
        raw_name = _dotted_name(node)
        if raw_name is None:
            return None
        head, separator, tail = raw_name.partition(".")
        canonical = self.function_aliases.get(head, self.module_aliases.get(head, head))
        return f"{canonical}.{tail}" if separator else canonical

    @staticmethod
    def _is_removed_zarr_name(name):
        return name in REMOVED_ZARR_SYMBOLS or any(
            name == prefix or name.startswith(f"{prefix}.") for prefix in REMOVED_ZARR_MODULE_PREFIXES
        )

    @staticmethod
    def _uses_mutable_mapping(annotation):
        if annotation is None:
            return False
        return any(
            _dotted_name(child) in {"MutableMapping", "collections.abc.MutableMapping", "typing.MutableMapping"}
            for child in ast.walk(annotation)
        )

    @staticmethod
    def _keyword(call, name):
        return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)

    def _mode(self, call):
        keyword_mode = self._keyword(call, "mode")
        if keyword_mode is not None:
            return keyword_mode
        return call.args[1] if len(call.args) > 1 else None

    def _has_required_format(self, call):
        format_value = self._keyword(call, "zarr_format")
        if self.path.startswith("tests/"):
            return format_value is not None
        return _is_constant(format_value, 2) or _is_constant(format_value, 3)

    @staticmethod
    def _is_typing_literal(node):
        name = _dotted_name(node)
        return name == "Literal" or name in {"typing.Literal", "typing_extensions.Literal"}

    @staticmethod
    def _is_array_listing(node):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "list":
            return False
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Call):
            return False
        return isinstance(node.args[0].func, ast.Attribute) and node.args[0].func.attr == "arrays"

    def visit_Import(self, node):
        for alias in node.names:
            if self._is_removed_zarr_name(alias.name):
                self._add(node, "removed_zarr_api", f"removed Zarr API imported: {alias.name}")
            if alias.name == "zarr" or alias.name.startswith("zarr.") or alias.name == "ome_zarr.writer":
                if alias.asname:
                    self.module_aliases[alias.asname] = alias.name
                else:
                    self.module_aliases[alias.name.split(".")[0]] = alias.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and (
            node.module == "zarr" or node.module.startswith("zarr.") or node.module == "ome_zarr.writer"
        ):
            for alias in node.names:
                imported_name = f"{node.module}.{alias.name}"
                if self._is_removed_zarr_name(imported_name):
                    self._add(node, "removed_zarr_api", f"removed Zarr API imported: {imported_name}")
                local_name = alias.asname or alias.name
                self.function_aliases[local_name] = imported_name
        elif node.module == "ome_zarr":
            for alias in node.names:
                if alias.name == "writer":
                    self.module_aliases[alias.asname or alias.name] = "ome_zarr.writer"
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        if node.name == "zarr" and self._uses_mutable_mapping(node.returns):
            self._add(node, "removed_zarr_api", "zarr() must return zarr.abc.store.Store, not MutableMapping")
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            if argument.arg in STORE_ARGUMENT_NAMES and self._uses_mutable_mapping(argument.annotation):
                self._add(
                    argument,
                    "removed_zarr_api",
                    f"store argument {argument.arg!r} must use zarr.abc.store.Store, not MutableMapping",
                )
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Assign(self, node):
        if self._is_array_listing(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.array_listing_names.add(target.id)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        name = self._canonical_name(node)
        if name and self._is_removed_zarr_name(name):
            self._add(node, "removed_zarr_api", f"removed Zarr API referenced: {name}")
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

                creates = entry_point not in ZARR_OPEN_ENTRY_POINTS or mode not in ZARR_NON_CREATING_MODES
                if creates and not self._has_required_format(node):
                    self._add(
                        node,
                        "explicit_zarr_format",
                        f"creation through zarr.{entry_point} requires an explicit supported zarr_format",
                    )

        if call_name == "ome_zarr.writer.write_multiscale":
            self._add(
                node,
                "removed_write_multiscale",
                "write_multiscale is not permitted after the canonical numeric-path writer cutover",
            )

        self.generic_visit(node)

    def visit_Subscript(self, node):
        if not isinstance(node.ctx, ast.Load):
            self.generic_visit(node)
            return

        if _is_constant(node.slice, "0") and not self._is_typing_literal(node.value):
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


def test_repository_obeys_zarr_structural_guards():
    source_paths = []
    for root in REPOSITORY_SCAN_ROOTS:
        assert root.is_dir(), f"Structural-guard scan root does not exist: {root}"
        root_sources = list(root.rglob("*.py"))
        assert root_sources, f"Structural-guard scan root contains no Python files: {root}"
        source_paths.extend(root_sources)

    violations = []
    for source_path in source_paths:
        relative_path = source_path.relative_to(PROJECT_ROOT).as_posix()
        violations.extend(find_violations(source_path.read_text(encoding="utf-8"), relative_path))

    observed_allowlist = {violation.allowlist_key for violation in violations} & ALLOWED_VIOLATIONS
    assert observed_allowlist == ALLOWED_VIOLATIONS, "Structural-guard allow-list contains stale entries"

    unexpected = [violation for violation in violations if violation.allowlist_key not in ALLOWED_VIOLATIONS]
    assert not unexpected, "Unexpected Zarr structural violations:\n" + "\n".join(map(str, unexpected))


@pytest.mark.parametrize("entry_point", sorted(ZARR_ENTRY_POINTS))
def test_guard_rejects_creation_without_explicit_v2_format(entry_point):
    arguments = "store, mode='w'" if entry_point in ZARR_OPEN_ENTRY_POINTS else "data"
    violations = find_violations(f"import zarr\nzarr.{entry_point}({arguments})\n")

    assert "explicit_zarr_format" in {violation.rule for violation in violations}


def test_guard_accepts_both_explicit_supported_production_formats():
    assert find_violations("import zarr\nzarr.group(store, zarr_format=2)\n") == []
    assert find_violations("import zarr\nzarr.group(store, zarr_format=3)\n") == []


@pytest.mark.parametrize("entry_point", sorted(ZARR_OPEN_ENTRY_POINTS))
def test_guard_treats_dynamic_open_modes_as_creation_capable(entry_point):
    violations = find_violations(f"import zarr\nzarr.{entry_point}(store, mode=mode)\n")

    assert "explicit_zarr_format" in {violation.rule for violation in violations}


@pytest.mark.parametrize("entry_point", sorted(ZARR_OPEN_ENTRY_POINTS))
def test_guard_rejects_open_without_explicit_mode(entry_point):
    violations = find_violations(f"import zarr\nzarr.{entry_point}(store, zarr_format=2)\n")

    assert "explicit_open_mode" in {violation.rule for violation in violations}


@pytest.mark.parametrize("fmt", ["", ", fmt=fmt"])
def test_guard_rejects_write_multiscale(fmt):
    source = f"from ome_zarr.writer import write_multiscale\nwrite_multiscale(images, group=group{fmt})\n"

    assert "removed_write_multiscale" in {violation.rule for violation in find_violations(source)}


@pytest.mark.parametrize(
    "source",
    [
        "import zarr.convenience as zc\nzc.open(store, mode='w')\n",
        "from zarr.convenience import open as zopen\nzopen(store, mode='w')\n",
        "import zarr.hierarchy as zh\nzh.open_group(store, mode='w')\n",
        "from zarr.hierarchy import open_group as zopen_group\nzopen_group(store, mode='w')\n",
        "from zarr import convenience as zc\nzc.open(store, mode='w')\n",
    ],
)
def test_guard_rejects_legacy_zarr_import_paths_without_explicit_v2_format(source):
    violations = find_violations(source)

    assert "explicit_zarr_format" in {violation.rule for violation in violations}


@pytest.mark.parametrize(
    "statement",
    [
        'array = grp["0"]',
        "array = group[str(level)]",
        "array = list(group.arrays())[0]",
        "arrays = list(group.arrays())\narray = arrays[0]",
    ],
)
def test_guard_rejects_level_reads_that_bypass_metadata(statement):
    violations = find_violations(
        f"def read(group, grp, level):\n    {statement.replace(chr(10), chr(10) + '    ')}\n",
    )

    assert "metadata_level_path" in {violation.rule for violation in violations}


def test_guard_accepts_explicit_v2_creation_and_metadata_level_resolution():
    source = """
import zarr
zarr.open(store, mode="w", zarr_format=2)
zarr.open_group(store, mode="w", zarr_format=2)
zarr.open_array(store, mode="w", zarr_format=2)
zarr.group(store, zarr_format=2)
zarr.create(shape, zarr_format=2)
zarr.array(data, zarr_format=2)
zarr.create_group(store, zarr_format=2)
zarr.create_array(store, zarr_format=2)
array = group[get_level_path(group, level)]
group.create_dataset("0", data=data)
assert "0" in group
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
        "removed_write_multiscale",
        "explicit_zarr_format",
    }


def test_guard_resolves_dotted_writer_import():
    source = "import ome_zarr.writer\nome_zarr.writer.write_multiscale(images, group=group)\n"

    assert "removed_write_multiscale" in {violation.rule for violation in find_violations(source)}


@pytest.mark.parametrize(
    "source",
    [
        "from zarr.storage import FSStore\n",
        "from zarr.storage import DirectoryStore as Store\n",
        "from zarr import copy_store\n",
        "import zarr.convenience\n",
        "import zarr.hierarchy as hierarchy\n",
        "import zarr\narray_type = zarr.core.Array\n",
    ],
)
def test_guard_rejects_removed_zarr_apis(source):
    assert "removed_zarr_api" in {violation.rule for violation in find_violations(source)}


@pytest.mark.parametrize(
    "source",
    [
        "from collections.abc import MutableMapping\n",
        "# FSStore and zarr.copy_store are historical names\n",
        "notes = 'DirectoryStore and zarr.convenience are not executable APIs'\n",
        "def describe() -> MutableMapping:\n    return metadata\n",
    ],
)
def test_guard_ignores_removed_api_names_outside_store_contracts(source):
    assert "removed_zarr_api" not in {violation.rule for violation in find_violations(source)}


@pytest.mark.parametrize(
    "source",
    [
        "def zarr(self) -> MutableMapping[str, bytes]:\n    return self.store\n",
        "def open_store(store: collections.abc.MutableMapping):\n    return store\n",
    ],
)
def test_guard_rejects_mutable_mapping_store_contracts(source):
    assert "removed_zarr_api" in {violation.rule for violation in find_violations(source)}
