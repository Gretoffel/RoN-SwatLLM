#!/usr/bin/env python3
## @file lint.py
## @brief Multi-language Coding Guidelines Checker.
#
#  Supported languages (auto-detected by file extension):
#    .py   Python  -- full AST + line checks
#    .lua  Lua     -- line + regex based checks
#    .c/.h C       -- line + regex based checks
#
#  Shared rules (all languages):
#    - Tabs for indentation, no trailing whitespace
#    - Line length warning at 120 chars
#    - 2 blank lines between top-level definitions
#    - Blank lines inside long functions (breathing room)
#    - Filename must be snake_case
#    - Doxygen block required above every function
#    - Naming: functions snake_case, classes/modules CamelCase,
#              vars camelCase, constants UPPER_CASE
#
#  Python-specific rules:
#    - No nested ternary, no lambda
#    - Max nesting depth 4
#    - Prefer match/case over 3+ chained if/elif
#    - Type hints required on all parameters and return values
#    - No bare except, avoid global
#    - Aligned assignments in consecutive blocks
#
#  Lua-specific rules:
#    - Doxygen via --- @brief / -- @param / -- @return (LDoc style)
#    - No x and y or z ternary pattern (use if/else)
#    - No inline semicolons joining statements
#    - No goto

import ast
import re
import sys
from pathlib import Path

# -- Config -------------------------------------------------------------------
MAX_LINE_LENGTH:      int = 120
MAX_NESTING:          int = 4
ELIF_MATCH_THRESHOLD: int = 2
DENSE_FUNC_LINES:     int = 15
# -----------------------------------------------------------------------------

NAMING_EXEMPT_PREFIXES: tuple[str, ...] = ("visit_", "test_", "setUp", "tearDown")

SUPPORTED_EXTENSIONS: dict[str, str] = {
	".py":  "python",
	".lua": "lua",
	".c":   "c",
	".h":   "c",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  SHARED INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════


class LintError:
	"""Represents a single guideline violation."""

	def __init__(self, path: str, line: int, rule: str, msg: str) -> None:
		"""Initialize a LintError with location and message."""
		self.path = path
		self.line = line
		self.rule = rule
		self.msg  = msg

	def __str__(self) -> str:
		"""Return a human-readable string representation."""
		loc = f"{self.path}:{self.line}" if self.line else self.path
		return f"{loc}  [{self.rule}]  {self.msg}"


## @brief Key function for sorting LintError objects by line number.
#  @param err The LintError to extract the sort key from.
#  @return    The line number integer.
def get_error_line(err: LintError) -> int:
	"""Return the line number of a LintError for use as a sort key."""
	return err.line


## @brief Check that the filename stem is snake_case.
#  @param path Path to the source file.
#  @return     List with one LintError if the name is invalid, else empty.
def check_filename(path: str) -> list[LintError]:
	"""Return a LintError if the filename is not snake_case."""
	errors: list[LintError] = []
	stem = Path(path).stem

	if not re.fullmatch(r"[a-z][a-z0-9_]*", stem):
		errors.append(LintError(path, 0, "FILENAME",
			f"Filename '{Path(path).name}' must be snake_case"))

	return errors


## @brief Check shared formatting rules using raw text only (no AST).
#
#  Checks trailing whitespace, space-based indentation, and line length.
#  Applies to all supported languages.
#
#  @param path   Path to the source file.
#  @param source Raw source text.
#  @return       List of LintError objects for formatting violations.
def check_lines_shared(path: str, source: str) -> list[LintError]:
	"""Check indentation, trailing whitespace, and line length for any language."""
	errors: list[LintError] = []

	for i, line in enumerate(source.splitlines(), start=1):

		if line != line.rstrip():
			errors.append(LintError(path, i, "TRAILING-WS",
				"Trailing whitespace at end of line"))

		stripped = line.lstrip("\t")
		leading  = line[: len(line) - len(stripped)]

		if " " in leading:
			errors.append(LintError(path, i, "INDENT-SPACES",
				"Indentation must use tabs, not spaces"))

		if len(line.expandtabs(4)) > MAX_LINE_LENGTH:
			errors.append(LintError(path, i, "LINE-LENGTH",
				f"Line is {len(line.expandtabs(4))} chars "
				f"(recommended max: {MAX_LINE_LENGTH})"))

	return errors


# ═══════════════════════════════════════════════════════════════════════════════
#  NAMING HELPERS  (shared across languages)
# ═══════════════════════════════════════════════════════════════════════════════


## @brief Check whether a name is snake_case.
#  @param name The identifier string to check.
#  @return True if the name matches snake_case, False otherwise.
def is_snake_case(name: str) -> bool:
	"""Return True if name is snake_case."""
	return bool(re.fullmatch(r"[a-z_][a-z0-9_]*", name))


## @brief Check whether a name is lowerCamelCase.
#  @param name The identifier string to check.
#  @return True if the name matches lowerCamelCase, False otherwise.
def is_camel_case(name: str) -> bool:
	"""Return True if name is lowerCamelCase."""
	return bool(re.fullmatch(r"[a-z][a-zA-Z0-9]*", name))


## @brief Check whether a name is UpperCamelCase (PascalCase).
#  @param name The identifier string to check.
#  @return True if the name matches PascalCase, False otherwise.
def is_pascal_case(name: str) -> bool:
	"""Return True if name is PascalCase."""
	return bool(re.fullmatch(r"[A-Z][a-zA-Z0-9]*", name))


## @brief Check whether a name is UPPER_CASE (constant style).
#  @param name The identifier string to check.
#  @return True if the name matches UPPER_CASE, False otherwise.
def is_upper_case(name: str) -> bool:
	"""Return True if name is UPPER_CASE."""
	return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", name))


## @brief Check whether a function name is exempt from snake_case enforcement.
#
#  Some names are required by external protocols (e.g. ast.NodeVisitor
#  demands visit_IfExp, visit_FunctionDef, etc.) and must not be renamed.
#
#  @param name The function name to check.
#  @return True if the name is protocol-mandated and should be skipped.
def is_naming_exempt(name: str) -> bool:
	"""Return True if the function name is exempt from snake_case checks."""
	for prefix in NAMING_EXEMPT_PREFIXES:
		if name.startswith(prefix):
			return True
	return False


# ═══════════════════════════════════════════════════════════════════════════════
#  PYTHON CHECKS
# ═══════════════════════════════════════════════════════════════════════════════


## @brief Check whether an AST node has a Python docstring as its first statement.
#  @param node The AST node (FunctionDef, ClassDef, etc.) to inspect.
#  @return True if a docstring is present, False otherwise.
def has_docstring(node: ast.AST) -> bool:
	"""Return True if the node starts with a string literal docstring."""
	return (
		hasattr(node, "body")
		and bool(node.body)  # type: ignore[attr-defined]
		and isinstance(node.body[0], ast.Expr)  # type: ignore[attr-defined]
		and isinstance(node.body[0].value, ast.Constant)
		and isinstance(node.body[0].value.value, str)
	)


## @brief Extract the Doxygen ## comment block directly above a given line.
#
#  Walks backwards from lineIdx collecting lines that start with # or ##.
#  Stops at the first line that is not a comment.
#
#  @param lines    All source lines of the file (0-indexed).
#  @param lineIdx  0-based index of the def/class line to look above.
#  @return         Joined text of the comment lines found, empty string if none.
def get_doxygen_block_py(lines: list[str], lineIdx: int) -> str:
	"""Walk backwards above lineIdx and collect the ## Doxygen comment block."""
	blockLines: list[str] = []
	i = lineIdx - 1

	while i >= 0:
		stripped = lines[i].strip()

		if stripped.startswith("#"):
			blockLines.insert(0, stripped)
			i -= 1
		else:
			break

	return "\n".join(blockLines)


## @brief Verify a Python Doxygen ## block for all required tags.
#
#  @param funcName   Name of the function (used in error messages).
#  @param blockText  Raw text of the ## comment block above the function.
#  @param paramNames List of parameter names (self/cls already excluded).
#  @param hasReturn  True if the function has a non-None return annotation.
#  @return           List of violation message strings (empty = all good).
def check_doxygen_tags_py(
	funcName:   str,
	blockText:  str,
	paramNames: list[str],
	hasReturn:  bool,
) -> list[str]:
	"""Check a Python ## Doxygen block for required tags."""
	issues: list[str] = []

	if not blockText:
		issues.append(f"Function '{funcName}': no Doxygen block found above def")
		return issues

	if not any(line.startswith("##") for line in blockText.splitlines()):
		issues.append(f"Function '{funcName}': Doxygen block must start with ## @brief")

	if "@brief" not in blockText:
		issues.append(f"Function '{funcName}': Doxygen block missing @brief")

	for paramName in paramNames:
		if f"@param {paramName}" not in blockText:
			issues.append(f"Function '{funcName}': Doxygen block missing @param {paramName}")

	if hasReturn and "@return" not in blockText:
		issues.append(f"Function '{funcName}': Doxygen block missing @return")

	return issues


## @brief Check all Python functions for valid ## Doxygen blocks above them.
#
#  @param path   Path to the source file (used in error messages).
#  @param source Raw source text of the file.
#  @param tree   Pre-parsed AST of the file.
#  @return       List of LintError objects for every Doxygen violation found.
def check_doxygen_blocks_py(path: str, source: str, tree: ast.AST) -> list[LintError]:
	"""Check every Python function for a valid ## Doxygen block above its def."""
	errors: list[LintError] = []
	lines = source.splitlines()

	for node in ast.walk(tree):
		if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			continue
		if node.name.startswith("__"):
			continue

		funcLineIdx = node.lineno - 1
		blockText   = get_doxygen_block_py(lines, funcLineIdx)

		allArgs = (
			node.args.args
			+ node.args.posonlyargs
			+ node.args.kwonlyargs
		)
		paramNames = [a.arg for a in allArgs if a.arg not in ("self", "cls")]

		hasReturn = (
			node.returns is not None
			and not (isinstance(node.returns, ast.Constant) and node.returns.value is None)
			and not (isinstance(node.returns, ast.Name) and node.returns.id == "None")
		)

		for msg in check_doxygen_tags_py(node.name, blockText, paramNames, hasReturn):
			errors.append(LintError(path, node.lineno, "DOXYGEN", msg))

	return errors


## @brief Require 2 blank lines before every top-level Python function or class.
#
#  Skips backwards over any ## / # Doxygen comment block before checking
#  so the blank lines are expected before the comment block, not inside it.
#
#  @param path   Path to the source file.
#  @param source Raw source text.
#  @return       List of LintError objects for blank-line violations.
def check_blank_lines_py(path: str, source: str) -> list[LintError]:
	"""Flag top-level Python definitions not preceded by 2 blank lines."""
	errors: list[LintError] = []
	lines = source.splitlines()

	try:
		tree = ast.parse(source)
	except SyntaxError:
		return errors

	topLevel: list[int] = sorted(
		node.lineno
		for node in ast.walk(tree)
		if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
		and node.col_offset == 0
	)

	for lineno in topLevel:
		idx = lineno - 1

		if idx < 2:
			continue

		scanIdx = idx - 1
		while scanIdx >= 0 and lines[scanIdx].strip().startswith("#"):
			scanIdx -= 1

		if scanIdx < 2:
			continue

		before1 = lines[scanIdx].strip()
		before2 = lines[scanIdx - 1].strip()

		if before1 != "" or before2 != "":
			errors.append(LintError(path, lineno, "BLANK-LINES",
				"Top-level function/class requires 2 blank lines before it"))

	return errors


## @brief Warn when a long Python function has no blank lines inside.
#
#  @param path   Path to the source file.
#  @param source Raw source text of the file.
#  @param tree   Pre-parsed AST of the file.
#  @return       List of LintError objects for dense function bodies.
def check_dense_functions_py(path: str, source: str, tree: ast.AST) -> list[LintError]:
	"""Flag Python functions over DENSE_FUNC_LINES with no blank lines inside."""
	errors: list[LintError] = []
	lines = source.splitlines()

	for node in ast.walk(tree):
		if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			continue

		startIdx = node.lineno
		endIdx   = node.end_lineno
		funcLen  = endIdx - startIdx

		if funcLen < DENSE_FUNC_LINES:
			continue

		bodyLines = lines[startIdx:endIdx]
		hasBlank  = any(line.strip() == "" for line in bodyLines)

		if not hasBlank:
			errors.append(LintError(path, node.lineno, "DENSE-FUNC",
				f"Function '{node.name}' is {funcLen} lines with no blank lines "
				f"-- add blank lines between logical sections"))

	return errors


## @brief Find the column of a bare = assignment operator on a line.
#
#  Returns -1 for lines that are not simple assignments (defs, ifs, augmented
#  assigns, comments, docstrings, decorators, etc.).
#
#  @param line A single source line without trailing newline.
#  @return     0-based column of the = character, or -1 if not an assignment.
def find_assign_col(line: str) -> int:
	"""Return the raw column of the bare = on an assignment line, or -1."""
	stripped = line.strip()

	TRIPLE_DOUBLE = chr(34) * 3
	TRIPLE_SINGLE = chr(39) * 3

	if (
		not stripped
		or stripped.startswith("#")
		or stripped.startswith(TRIPLE_DOUBLE)
		or stripped.startswith(TRIPLE_SINGLE)
		or stripped.startswith("def ")
		or stripped.startswith("class ")
		or stripped.startswith("@")
		or stripped.startswith("return ")
		or stripped.startswith("if ")
		or stripped.startswith("elif ")
		or stripped.startswith("while ")
		or stripped.startswith("for ")
	):
		return -1

	inSingle = False
	inDouble = False
	prev     = ""

	for idx, ch in enumerate(line):
		if ch == "'" and not inDouble:
			inSingle = not inSingle
		elif ch == '"' and not inSingle:
			inDouble = not inDouble

		if inSingle or inDouble:
			prev = ch
			continue

		if ch == "=" and prev not in ("!", "<", ">", "=", ":"):
			nextCh = line[idx + 1] if idx + 1 < len(line) else ""
			if nextCh != "=":
				return idx

		prev = ch

	return -1


## @brief Check that consecutive Python assignment blocks have aligned = signs.
#
#  Groups consecutive assignment lines that share the same indent level and
#  LHS prefix (e.g. all self.*).  Bare-name assignments are only grouped
#  when the author has already added padding, indicating intentional alignment.
#
#  @param path   Path to the source file.
#  @param source Raw source text.
#  @return       List of LintError objects for misaligned assignments.
def check_aligned_assignments(path: str, source: str) -> list[LintError]:
	"""Flag consecutive assignment blocks where the = signs are not aligned."""
	errors: list[LintError]                = []
	rawLines                               = source.splitlines()
	assignInfo: list[tuple[int, int, str]] = []

	for idx, line in enumerate(rawLines, start=1):
		col = find_assign_col(line)
		lhs = line.strip().split("=")[0].strip() if col >= 0 else ""
		assignInfo.append((idx, col, lhs))

	i = 0
	while i < len(assignInfo):
		lineNum, col, lhs = assignInfo[i]

		if col == -1:
			i += 1
			continue

		group: list[tuple[int, int]] = [(lineNum, col)]
		j                            = i + 1

		while j < len(assignInfo):
			nextLineNum, nextCol, nextLhs = assignInfo[j]

			if rawLines[nextLineNum - 1].strip() == "" or nextCol == -1:
				break

			currIndent = len(rawLines[lineNum - 1]) - len(rawLines[lineNum - 1].lstrip("\t"))
			nextIndent = len(rawLines[nextLineNum - 1]) - len(rawLines[nextLineNum - 1].lstrip("\t"))
			if currIndent != nextIndent:
				break

			currPrefix = lhs.split(".")[0] if "." in lhs else ""
			nextPrefix = nextLhs.split(".")[0] if "." in nextLhs else ""
			if currPrefix != nextPrefix:
				break

			if currPrefix == "":
				alreadyPadded = (col > len(lhs) + 2) or (nextCol > len(nextLhs) + 2)
				if not alreadyPadded:
					break

			group.append((nextLineNum, nextCol))
			j += 1

		if len(group) >= 2:
			maxCol = max(c for _, c in group)

			for gLineNum, gCol in group:
				if gCol != maxCol:
					errors.append(LintError(path, gLineNum, "ALIGN-ASSIGN",
						f"Assignment = at column {gCol}, expected {maxCol} "
						f"-- align = with the rest of the block"))

		i = j if j > i + 1 else i + 1

	return errors


class ASTChecker(ast.NodeVisitor):
	"""Walks the Python AST and collects guideline violations."""

	def __init__(self, path: str) -> None:
		"""Initialize the checker with the source file path."""
		self.path                      = path
		self.errors: list[LintError]   = []
		self._depth                    = 0
		self._inTernary                = False

	## @brief Append a LintError to the internal error list.
	#  @param node AST node the violation occurred at.
	#  @param rule Short rule identifier string.
	#  @param msg  Human-readable description of the violation.
	def _err(self, node: ast.AST, rule: str, msg: str) -> None:
		"""Append a new LintError for the given node."""
		self.errors.append(
			LintError(self.path, getattr(node, "lineno", 0), rule, msg)
		)

	# AST visitor methods follow the ast.NodeVisitor protocol naming convention
	# (visit_<NodeType>) and are therefore exempt from snake_case enforcement.

## @brief Visit a ternary expression and flag nested ternaries.
#  @param node The IfExp AST node being visited.
	def visit_IfExp(self, node: ast.IfExp) -> None:
		"""Visit a ternary expression and flag nested ternaries."""
		if self._inTernary:
			self._err(node, "NESTED-TERNARY",
				"Nested ternary not allowed -- use if/else instead")

		saved           = self._inTernary
		self._inTernary = True
		self.generic_visit(node)
		self._inTernary = saved

## @brief Visit a lambda expression and flag it as a violation.
#  @param node The Lambda AST node being visited.
	def visit_Lambda(self, node: ast.Lambda) -> None:
		"""Visit a lambda expression and flag it as a violation."""
		self._err(node, "NO-LAMBDA",
			"Lambda not allowed -- define a named function instead")
		self.generic_visit(node)

## @brief Visit an except clause and flag bare except without a type.
#  @param node The ExceptHandler AST node being visited.
	def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
		"""Visit an except clause and flag bare except."""
		if node.type is None:
			self._err(node, "NO-BARE-EXCEPT",
				"Bare `except:` not allowed -- specify type e.g. `except ValueError:`")
		self.generic_visit(node)

## @brief Visit a global statement and flag it as a guideline violation.
#  @param node The Global AST node being visited.
	def visit_Global(self, node: ast.Global) -> None:
		"""Visit a global statement and flag it."""
		names = ", ".join(node.names)
		self._err(node, "GLOBAL", f"Avoid globals: `global {names}`")
		self.generic_visit(node)

	## @brief Perform all checks on a single function definition node.
	#  @param node The FunctionDef or AsyncFunctionDef node to check.
	def _check_function(self, node: ast.FunctionDef) -> None:
		"""Run naming, docstring, type-hint, and nesting checks on a function."""
		isDunder = node.name.startswith("__")
		isExempt = is_naming_exempt(node.name)

		if not isDunder and not isExempt and not is_snake_case(node.name):
			self._err(node, "NAMING-FUNC",
				f"Function '{node.name}' must be snake_case")

		if not has_docstring(node):
			self._err(node, "DOCSTRING",
				f"Function '{node.name}' requires an internal docstring")

		if node.returns is None and not isDunder:
			self._err(node, "TYPE-HINT",
				f"Function '{node.name}' requires a return type hint")

		allArgs = (
			node.args.args
			+ node.args.posonlyargs
			+ node.args.kwonlyargs
		)
		for arg in allArgs:
			if arg.annotation is None and arg.arg not in ("self", "cls"):
				self._err(node, "TYPE-HINT",
					f"Parameter '{arg.arg}' in '{node.name}' requires a type hint")

		saved       = self._depth
		self._depth = 0
		self.generic_visit(node)
		self._depth = saved

## @brief Visit a function definition and run all function checks.
#  @param node The FunctionDef AST node being visited.
	def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
		"""Visit a function definition node."""
		self._check_function(node)

## @brief Visit an async function definition and run all function checks.
#  @param node The AsyncFunctionDef AST node being visited.
	def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
		"""Visit an async function definition node."""
		self._check_function(node)  # type: ignore[arg-type]

## @brief Visit a class definition and check naming and docstring.
#  @param node The ClassDef AST node being visited.
	def visit_ClassDef(self, node: ast.ClassDef) -> None:
		"""Visit a class definition and check naming and docstring."""
		if not is_pascal_case(node.name):
			self._err(node, "NAMING-CLASS",
				f"Class '{node.name}' must be CamelCase e.g. MyClass")

		if not has_docstring(node):
			self._err(node, "DOCSTRING",
				f"Class '{node.name}' requires a docstring")

		self.generic_visit(node)

	## @brief Check a single variable name assignment for correct casing.
	#  @param node The AST node of the assignment target.
	#  @param name The variable name string to check.
	def _check_var_name(self, node: ast.AST, name: str) -> None:
		"""Flag variable names that are not camelCase or UPPER_CASE."""
		if name.startswith("_") or len(name) == 1:
			return

		if is_upper_case(name):
			return

		if not is_camel_case(name):
			self._err(node, "NAMING-VAR",
				f"Variable '{name}' must be camelCase or UPPER_CASE (constants)")

## @brief Visit an assignment statement and check variable naming.
#  @param node The Assign AST node being visited.
	def visit_Assign(self, node: ast.Assign) -> None:
		"""Visit an assignment and check variable naming."""
		for target in node.targets:
			if isinstance(target, ast.Name):
				self._check_var_name(target, target.id)
		self.generic_visit(node)

## @brief Visit an annotated assignment and check variable naming.
#  @param node The AnnAssign AST node being visited.
	def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
		"""Visit an annotated assignment and check variable naming."""
		if isinstance(node.target, ast.Name):
			self._check_var_name(node.target, node.target.id)
		self.generic_visit(node)

	## @brief Increment nesting depth, check limit, recurse, then decrement.
	#  @param node The AST node that opens a new nesting level.
	def _visit_nesting(self, node: ast.AST) -> None:
		"""Track nesting depth and flag violations above MAX_NESTING."""
		self._depth += 1

		if self._depth > MAX_NESTING:
			self._err(node, "MAX-NESTING",
				f"Nesting depth {self._depth} exceeds maximum of {MAX_NESTING}")

		self.generic_visit(node)
		self._depth -= 1

## @brief Visit an if statement, check chained elif count, then nesting.
#  @param node The If AST node being visited.
	def visit_If(self, node: ast.If) -> None:
		"""Visit an if statement, check chained elif count, then nesting."""
		elifCount = 0
		current   = node

		while (
			current.orelse
			and len(current.orelse) == 1
			and isinstance(current.orelse[0], ast.If)
		):
			elifCount     += 1
			current        = current.orelse[0]

		if elifCount >= ELIF_MATCH_THRESHOLD:
			self._err(node, "PREFER-MATCH",
				"3+ chained if/elif branches -- consider using match/case instead")

		self._visit_nesting(node)

## @brief Visit a for loop and track nesting depth.
#  @param node The For AST node being visited.
	def visit_For(self, node: ast.For) -> None:
		"""Visit a for loop and track nesting depth."""
		self._visit_nesting(node)

## @brief Visit a while loop and track nesting depth.
#  @param node The While AST node being visited.
	def visit_While(self, node: ast.While) -> None:
		"""Visit a while loop and track nesting depth."""
		self._visit_nesting(node)

## @brief Visit a with block and track nesting depth.
#  @param node The With AST node being visited.
	def visit_With(self, node: ast.With) -> None:
		"""Visit a with block and track nesting depth."""
		self._visit_nesting(node)

## @brief Visit a try block and track nesting depth.
#  @param node The Try AST node being visited.
	def visit_Try(self, node: ast.Try) -> None:
		"""Visit a try block and track nesting depth."""
		self._visit_nesting(node)


## @brief Run all Python-specific checks on a single file.
#  @param path   Path to the .py file.
#  @param source Raw source text.
#  @return       Sorted list of LintError objects.
def lint_python(path: str, source: str) -> list[LintError]:
	"""Run every Python linting pass and return sorted results."""
	errors: list[LintError] = []

	errors.extend(check_lines_shared(path, source))
	errors.extend(check_blank_lines_py(path, source))
	errors.extend(check_aligned_assignments(path, source))

	try:
		tree = ast.parse(source, filename=path)
	except SyntaxError as exc:
		errors.append(LintError(path, exc.lineno or 0, "SYNTAX", str(exc)))
		return sorted(errors, key=get_error_line)

	checker = ASTChecker(path)
	checker.visit(tree)
	errors.extend(checker.errors)

	errors.extend(check_doxygen_blocks_py(path, source, tree))
	errors.extend(check_dense_functions_py(path, source, tree))

	return errors


# ═══════════════════════════════════════════════════════════════════════════════
#  LUA CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

# Lua function patterns:
#   function my_func(...)         -- global function
#   local function my_func(...)   -- local function
#   function MyClass:my_method(   -- method
LUA_FUNC_RE = re.compile(
	r"^(?:local\s+)?function\s+([\w.:]+)\s*\("
)

# Lua "ternary" anti-pattern:  x and y or z
LUA_TERNARY_RE = re.compile(r"\band\b.+\bor\b")

# Inline semicolons joining two statements on one line:  stmt ; stmt
LUA_SEMICOLON_RE = re.compile(r";\s*\S")

# goto keyword
LUA_GOTO_RE = re.compile(r"\bgoto\b")

# local variable declaration:  local myVar = ...
LUA_LOCAL_VAR_RE = re.compile(r"^\s*local\s+([A-Za-z_][A-Za-z0-9_]*)\s*=")

# constant heuristic: local MY_CONST = literal (string/number/true/false)
LUA_CONST_RE = re.compile(
	r"^\s*local\s+([A-Z][A-Z0-9_]+)\s*=\s*(?:[\"'\d]|true|false)"
)


## @brief Extract the LDoc --- comment block directly above a given line.
#
#  LDoc / Doxygen-for-Lua style uses --- for the opening line and -- for
#  continuation lines.  Walks backwards collecting comment lines.
#
#  @param lines    All source lines of the file (0-indexed).
#  @param lineIdx  0-based index of the function line to look above.
#  @return         Joined text of the comment lines, empty string if none.
def get_doxygen_block_lua(lines: list[str], lineIdx: int) -> str:
	"""Walk backwards above lineIdx and collect the --- LDoc comment block."""
	blockLines: list[str] = []
	i = lineIdx - 1

	while i >= 0:
		stripped = lines[i].strip()

		if stripped.startswith("--"):
			blockLines.insert(0, stripped)
			i -= 1
		else:
			break

	return "\n".join(blockLines)


## @brief Verify a Lua LDoc comment block for all required Doxygen tags.
#
#  The opening line must start with --- (three dashes).
#  Uses @brief, @param, @return identical to Python convention.
#
#  @param funcName   Name of the function (used in error messages).
#  @param blockText  Raw text of the --- comment block above the function.
#  @param paramNames List of parameter names to check.
#  @param hasReturn  True when the function is expected to return a value.
#  @return           List of violation message strings (empty = all good).
def check_doxygen_tags_lua(
	funcName:   str,
	blockText:  str,
	paramNames: list[str],
	hasReturn:  bool,
) -> list[str]:
	"""Check a Lua --- LDoc block for required Doxygen tags."""
	issues: list[str] = []

	if not blockText:
		issues.append(f"Function '{funcName}': no LDoc block found above function")
		return issues

	if not any(line.startswith("---") for line in blockText.splitlines()):
		issues.append(f"Function '{funcName}': LDoc block must start with --- @brief")

	if "@brief" not in blockText:
		issues.append(f"Function '{funcName}': LDoc block missing @brief")

	for paramName in paramNames:
		if f"@param {paramName}" not in blockText:
			issues.append(f"Function '{funcName}': LDoc block missing @param {paramName}")

	if hasReturn and "@return" not in blockText:
		issues.append(f"Function '{funcName}': LDoc block missing @return")

	return issues


## @brief Run all Lua-specific checks on a single file.
#
#  Uses regex and line scanning (no AST available for Lua).
#  Checks: shared formatting, Doxygen LDoc blocks, naming conventions,
#  no and/or ternary pattern, no inline semicolons, no goto.
#
#  @param path   Path to the .lua file.
#  @param source Raw source text.
#  @return       Sorted list of LintError objects.
def lint_lua(path: str, source: str) -> list[LintError]:
	"""Run every Lua linting pass and return sorted results."""
	errors: list[LintError] = []
	lines = source.splitlines()

	errors.extend(check_lines_shared(path, source))

	for i, line in enumerate(lines, start=1):
		stripped = line.strip()

		# Skip pure comment lines for most checks
		isComment = stripped.startswith("--")

		if not isComment:

			# No and/or ternary pattern
			if LUA_TERNARY_RE.search(line):
				errors.append(LintError(path, i, "LUA-TERNARY",
					"Avoid `x and y or z` ternary -- use if/else instead"))

			# No inline semicolons
			if LUA_SEMICOLON_RE.search(line):
				errors.append(LintError(path, i, "LUA-SEMICOLON",
					"Inline semicolon joining statements -- split into separate lines"))

			# No goto
			if LUA_GOTO_RE.search(line):
				errors.append(LintError(path, i, "LUA-GOTO",
					"goto is not allowed"))

			# Variable naming
			varMatch = LUA_LOCAL_VAR_RE.match(line)
			if varMatch:
				varName = varMatch.group(1)

				if not is_upper_case(varName) and not is_camel_case(varName) and len(varName) > 1:
					errors.append(LintError(path, i, "NAMING-VAR",
						f"Variable '{varName}' must be camelCase or UPPER_CASE (constants)"))

		# Function definition checks
		funcMatch = LUA_FUNC_RE.match(stripped)
		if funcMatch:
			rawName  = funcMatch.group(1)
			funcName = rawName.split(".")[-1].split(":")[-1]

			# Naming
			if not is_snake_case(funcName) and not is_naming_exempt(funcName):
				errors.append(LintError(path, i, "NAMING-FUNC",
					f"Function '{funcName}' must be snake_case"))

			# Doxygen LDoc block
			lineIdx   = i - 1
			blockText = get_doxygen_block_lua(lines, lineIdx)

			# Naively extract param names from the function signature
			sigLine               = stripped
			parenOpen             = sigLine.find("(")
			parenClose            = sigLine.find(")")
			paramNames: list[str] = []

			if parenOpen >= 0 and parenClose > parenOpen:
				paramStr   = sigLine[parenOpen + 1:parenClose]
				paramNames = [
					p.strip() for p in paramStr.split(",")
					if p.strip() and p.strip() != "self"
				]

			# Heuristic: assume return if next non-blank/comment line has 'return'
			hasReturn = False
			for nextLine in lines[i:i + 60]:
				ns = nextLine.strip()
				if ns.startswith("end") or ns.startswith("return"):
					hasReturn = ns.startswith("return") and ns != "return"
					break

			for msg in check_doxygen_tags_lua(funcName, blockText, paramNames, hasReturn):
				errors.append(LintError(path, i, "DOXYGEN", msg))

	# Blank lines between top-level functions (simple line scan)
	prevFuncLine = -1
	for i, line in enumerate(lines, start=1):
		if LUA_FUNC_RE.match(line.strip()) and not line.strip().startswith("local"):
			if prevFuncLine > 0:
				gapLines   = lines[prevFuncLine:i - 1]
				blankCount = sum(1 for l in gapLines if l.strip() == "")

				if blankCount < 2:
					errors.append(LintError(path, i, "BLANK-LINES",
						"Top-level function requires 2 blank lines before it"))

			prevFuncLine = i

	return errors


# ═══════════════════════════════════════════════════════════════════════════════
#  C CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

# C function definition: captures the function name (identifier before the
# opening paren).  Matches K&R style (brace on same line) and Allman
# style (brace on next line -- line ends with closing paren).
# __attribute__(...) is stripped before matching.
C_FUNC_RE = re.compile(
	r"^"
	r"(?:(?:static|inline|extern|const|volatile|unsigned|signed|long|short)\s+)*"
	r"(?:(?:struct|union|enum)\s+)?"
	r"[\w\*][\w\s\*]*?"
	r"\b([a-zA-Z_]\w*)"
	r"\s*\("
	r"[^;]*"
	r"\)"
	r"\s*(?:\{|$)"
)

# Keywords that look like function calls but are not functions
C_KEYWORDS: frozenset[str] = frozenset({
	"if", "for", "while", "switch", "do", "return",
	"else", "case", "default", "sizeof", "typedef",
})

# #define constant naming check
C_DEFINE_RE = re.compile(r"^#define\s+([A-Za-z_][A-Za-z0-9_]*)")

# Local variable declaration heuristic
C_VAR_DECL_RE = re.compile(
	r"^\s*(?:(?:const|static|unsigned|signed|long|short)\s+)*"
	r"(?:int|char|float|double|bool|void|size_t|uint\w*|int\w*|\w+_t)"
	r"\s+\*?\s*([A-Za-z_][A-Za-z0-9_]*)"
	r"\s*(?:=|;|,)"
)


## @brief Strip GCC __attribute__((...)) annotations from a line.
#  @param line A single source line to clean.
#  @return     The line with all __attribute__(...) occurrences removed.
def strip_c_attributes(line: str) -> str:
	"""Remove __attribute__((...)) so the function regex works."""
	return re.sub(r"__attribute__\s*\(\([^)]*\)\)", "", line)


## @brief Match a C function definition line and return the function name.
#
#  Handles K&R and Allman brace styles.  Strips __attribute__ annotations.
#  Returns None for C keywords, declarations ending in ;, and non-functions.
#
#  @param line A single source line.
#  @return     Function name string, or None if not a function definition.
def match_c_func(line: str) -> str | None:
	"""Return the C function name if line is a definition, else None."""
	cleaned = strip_c_attributes(line)
	m       = C_FUNC_RE.match(cleaned)

	if not m:
		return None

	name = m.group(1)

	if name in C_KEYWORDS:
		return None

	if line.rstrip().endswith(";"):
		return None

	return name


## @brief Extract the Doxygen /** ... */ block directly above a C function.
#
#  Walks backwards collecting comment lines that belong to a /** block.
#  Also accepts /// line-comment style.  Stops at /** (opening line).
#
#  @param lines    All source lines of the file (0-indexed).
#  @param lineIdx  0-based index of the function definition line.
#  @return         Joined text of the comment block, empty string if none.
def get_doxygen_block_c(lines: list[str], lineIdx: int) -> str:
	"""Walk backwards above lineIdx and collect the /** or /// Doxygen block."""
	blockLines: list[str] = []
	i = lineIdx - 1

	while i >= 0:
		stripped = lines[i].strip()

		if (
			stripped.startswith("*")
			or stripped.startswith("/**")
			or stripped.startswith("///")
			or stripped.startswith("//!")
		):
			blockLines.insert(0, stripped)

			if stripped.startswith("/**"):
				break

			i -= 1
		else:
			break

	return "\n".join(blockLines)


## @brief Verify a C Doxygen /** ... */ block for all required tags.
#
#  @param funcName   Name of the function (used in error messages).
#  @param blockText  Raw text of the Doxygen block above the function.
#  @param paramNames List of parameter names to check.
#  @param hasReturn  True when the function return type is not void.
#  @return           List of violation message strings (empty = all good).
def check_doxygen_tags_c(
	funcName:   str,
	blockText:  str,
	paramNames: list[str],
	hasReturn:  bool,
) -> list[str]:
	"""Check a C /** Doxygen block for required tags."""
	issues: list[str] = []

	if not blockText:
		issues.append(f"Function '{funcName}': no Doxygen block found above definition")
		return issues

	hasOpener = (
		any(l.startswith("/**") for l in blockText.splitlines())
		or any(l.startswith("///") for l in blockText.splitlines())
	)
	if not hasOpener:
		issues.append(f"Function '{funcName}': Doxygen block must open with /** or ///")

	if "@brief" not in blockText:
		issues.append(f"Function '{funcName}': Doxygen block missing @brief")

	for paramName in paramNames:
		if f"@param {paramName}" not in blockText:
			issues.append(f"Function '{funcName}': Doxygen block missing @param {paramName}")

	if hasReturn and "@return" not in blockText:
		issues.append(f"Function '{funcName}': Doxygen block missing @return")

	return issues


## @brief Parse parameter names from a C function signature line.
#
#  Strips type qualifiers and pointer stars to extract just the variable
#  name from each parameter.  Returns empty list for void functions.
#
#  @param sigLine The full function definition line as a string.
#  @return        List of parameter name strings.
def parse_c_params(sigLine: str) -> list[str]:
	"""Extract parameter names from a C function signature line."""
	parenOpen  = sigLine.find("(")
	parenClose = sigLine.rfind(")")

	if parenOpen < 0 or parenClose <= parenOpen:
		return []

	paramStr = sigLine[parenOpen + 1:parenClose].strip()

	if not paramStr or paramStr == "void":
		return []

	QUALIFIERS: frozenset[str] = frozenset({
		"const", "unsigned", "signed", "long", "short",
		"static", "register", "volatile", "restrict",
		"int", "char", "float", "double", "void", "bool", "size_t",
	})

	paramNames: list[str] = []

	for param in paramStr.split(","):
		tokens = [t.strip("* \t") for t in param.strip().split()]
		tokens = [t for t in tokens if t]

		name = ""
		for tok in reversed(tokens):
			if tok not in QUALIFIERS and re.fullmatch(r"[A-Za-z_]\w*", tok):
				name = tok
				break

		if name and name not in QUALIFIERS:
			paramNames.append(name)

	return paramNames


## @brief Determine whether a C function has a non-void return type.
#
#  void* is treated as a return value (returns a pointer).
#  Bare void is treated as no return value.
#
#  @param line The function definition line.
#  @return     True if the return type is not bare void.
def c_has_return(line: str) -> bool:
	"""Return True if the C function line has a non-void return type."""
	beforeParens = line[:line.find("(")].strip()
	tokens       = beforeParens.split()

	if "void" in tokens and "*" not in beforeParens:
		return False

	return True


## @brief Check that top-level C functions are separated by 2 blank lines.
#  @param path   Path to the source file.
#  @param source Raw source text.
#  @return       List of LintError objects for blank-line violations.
def check_c_blank_lines(path: str, source: str) -> list[LintError]:
	"""Flag C top-level functions not preceded by 2 blank lines."""
	errors: list[LintError] = []

	rawLines     = source.splitlines()
	prevFuncLine = -1

	for i, line in enumerate(rawLines, start=1):
		name = match_c_func(line)

		if name is None:
			continue

		if prevFuncLine > 0:
			gapLines   = rawLines[prevFuncLine:i - 1]
			blankCount = sum(1 for l in gapLines if l.strip() == "")

			if blankCount < 2:
				errors.append(LintError(path, i, "BLANK-LINES",
					"Top-level function requires 2 blank lines before it"))

		prevFuncLine = i

	return errors


## @brief Run all C-specific checks on a single .c or .h file.
#
#  Uses regex and line scanning (no AST available for C).
#  Checks: shared formatting, Doxygen /** blocks, naming,
#  no goto, #define constant naming, 2 blank lines between functions.
#
#  @param path   Path to the .c or .h file.
#  @param source Raw source text.
#  @return       List of LintError objects.
def lint_c(path: str, source: str) -> list[LintError]:
	"""Run every C linting pass and return results."""
	errors: list[LintError] = []

	lines          = source.splitlines()
	inBlockComment = False

	errors.extend(check_lines_shared(path, source))

	for i, line in enumerate(lines, start=1):
		stripped = line.strip()

		# Track /* ... */ block comment state
		if "/*" in line and "*/" not in line:
			inBlockComment = True
		elif "*/" in line:
			inBlockComment = False
			continue

		isComment = (
			inBlockComment
			or stripped.startswith("//")
			or stripped.startswith("*")
		)

		if not isComment and stripped:


			# #define constant naming
			defineMatch = C_DEFINE_RE.match(stripped)
			if defineMatch:
				defineName = defineMatch.group(1)
				if not is_upper_case(defineName) and not defineName.startswith("_"):
					errors.append(LintError(path, i, "NAMING-DEFINE",
						f"#define '{defineName}' should be UPPER_CASE"))

			# Variable declaration naming
			varMatch = C_VAR_DECL_RE.match(line)
			if varMatch:
				varName = varMatch.group(1)
				if (
					len(varName) > 1
					and not varName.startswith("_")
					and not is_upper_case(varName)
					and not is_camel_case(varName)
				):
					errors.append(LintError(path, i, "NAMING-VAR",
						f"Variable '{varName}' must be camelCase or UPPER_CASE"))

		# Function definition checks (outside block comments)
		if not inBlockComment:
			funcName = match_c_func(line)

			if funcName is not None:

				if not is_snake_case(funcName) and not is_naming_exempt(funcName):
					errors.append(LintError(path, i, "NAMING-FUNC",
						f"Function '{funcName}' must be snake_case"))

				blockText = get_doxygen_block_c(lines, i - 1)
				params    = parse_c_params(line)
				hasRet    = c_has_return(line)

				for msg in check_doxygen_tags_c(funcName, blockText, params, hasRet):
					errors.append(LintError(path, i, "DOXYGEN", msg))

	errors.extend(check_c_blank_lines(path, source))

	return errors

# ═══════════════════════════════════════════════════════════════════════════════
#  DISPATCH
# ═══════════════════════════════════════════════════════════════════════════════


## @brief Detect file language from extension and run the correct linter.
#  @param path Path to the source file to lint.
#  @return     Sorted list of LintError objects, or empty list on read error.
def lint_file(path: str) -> list[LintError]:
	"""Detect language by extension, run the appropriate linter, return results."""
	errors: list[LintError] = []

	ext    = Path(path).suffix.lower()
	lang   = SUPPORTED_EXTENSIONS.get(ext)

	errors.extend(check_filename(path))

	if lang is None:
		errors.append(LintError(path, 0, "UNSUPPORTED",
			f"Unsupported file type '{ext}' "
			f"-- supported: {', '.join(SUPPORTED_EXTENSIONS.keys())}"))
		return errors

	try:
		source = Path(path).read_text(encoding="utf-8")
	except OSError as exc:
		print(f"[ERROR] Cannot read '{path}': {exc}")
		return []

	match lang:
		case "python":
			errors.extend(lint_python(path, source))
		case "lua":
			errors.extend(lint_lua(path, source))
		case "c":
			errors.extend(lint_c(path, source))

	return sorted(errors, key=get_error_line)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


## @brief Resolve a single CLI argument to a list of file paths.
#
#  Handles four cases:
#    1. Exact file path that exists            → [path]
#    2. Glob pattern (contains * or ?)        → expanded list
#    3. Directory                              → all supported files recursively
#    4. Nothing matched                        → empty list + warning printed
#
#  @param arg The raw CLI argument string.
#  @return    List of resolved file path strings.
def resolve_arg(arg: str) -> list[str]:
	"""Expand a CLI argument into a list of concrete file paths."""
	argPath = Path(arg)

	# Case 1: exact file
	if argPath.is_file():
		return [str(argPath)]

	# Case 2: glob pattern (Windows doesn't expand these in the shell)
	if "*" in arg or "?" in arg:
		base    = Path(arg).parent
		pattern = Path(arg).name

		if not base.exists():
			base = Path(".")

		matched = sorted(base.glob(pattern))
		result  = [str(p) for p in matched if p.is_file()]

		if not result:
			print(f"[WARN] No files matched: {arg}")

		return result

	# Case 3: directory → recurse, collect all supported extensions
	if argPath.is_dir():
		result = []

		for ext in SUPPORTED_EXTENSIONS:
			result.extend(str(p) for p in sorted(argPath.rglob(f"*{ext}")))

		if not result:
			print(f"[WARN] No supported files found in: {arg}")

		return result

	# Case 4: nothing matched
	print(f"[WARN] Path not found: {arg}")
	return []


## @brief CLI entry point -- accepts files, globs, and directories.
#
#  Examples:
#    python lint.py src/main.py
#    python lint.py src/
#    python lint.py src/*.lua          (works on Windows too)
#    python lint.py src/ tests/ main.c
#
#  @param None
#  @return None
def main() -> None:
	"""Parse CLI arguments, resolve paths, and run lint_file on each file."""
	if len(sys.argv) < 2:
		print("Usage: python lint.py <file|dir|glob> [...]")
		print(f"Supported: {', '.join(SUPPORTED_EXTENSIONS.keys())}")
		sys.exit(1)

	allErrors: list[LintError] = []
	filesSeen: set[str]        = set()

	for arg in sys.argv[1:]:
		for path in resolve_arg(arg):

			# Deduplicate in case multiple globs match the same file
			if path in filesSeen:
				continue
			filesSeen.add(path)

			fileErrors = lint_file(path)

			for err in fileErrors:
				print(err)

			allErrors.extend(fileErrors)

	if not allErrors:
		print("OK -- no violations found")
		sys.exit(0)

	print(f"\nFAIL -- {len(allErrors)} violation(s) found")
	sys.exit(1)


if __name__ == "__main__":
	main()
