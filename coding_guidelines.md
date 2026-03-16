# Python Coding Guidelines

> Binding rules for all Python projects.  
> Violations are automatically caught by `lint.py`.

---

## Table of Contents

1. [Formatting](#1-formatting)
2. [Code Structure](#2-code-structure)
3. [Naming Conventions](#3-naming-conventions)
4. [Types & Documentation](#4-types--documentation)
5. [Error Handling](#5-error-handling)
6. [Global Variables](#6-global-variables)
7. [Configuration](#7-configuration)
8. [File Structure](#8-file-structure)
9. [Quick Reference](#9-quick-reference)

---

## 1. Formatting

### 1.1 Indentation

Indentation uses **tabs exclusively**. Spaces for indentation are forbidden.  
1 tab = 4 spaces visual width. Configure your editor accordingly.

```python
# ✓ Correct
def calculate_total(price: float, tax: float) -> float:
	result = price + tax
	return result

# ✗ Wrong -- spaces instead of tabs
def calculate_total(price: float, tax: float) -> float:
    result = price + tax   # spaces!
    return result
```

### 1.2 Line Length

There is no hard limit. A **warning is issued at 120 characters** (measured with tab width = 4).  
Very long lines should be avoided — they hurt readability in side-by-side diffs and code review.

Break long expressions using parentheses:

```python
# ✓ Correct -- wrap with parentheses
result = (
	some_long_variable_name
	+ another_long_variable_name
	+ yet_another_one
)

# ✓ Correct -- break function arguments
send_notification(
	recipient=user,
	subject="Order confirmed",
	body=messageBody,
)
```

### 1.3 Blank Lines

Exactly **2 blank lines** between every top-level function and class definition.  
Inside a class, **1 blank line** between methods.

```python
import os


def first_function() -> None:
	"""First function."""
	pass


def second_function() -> None:
	"""Second function."""
	pass


class MyClass:
	"""A class."""

	def method_one(self) -> None:
		"""First method."""
		pass

	def method_two(self) -> None:
		"""Second method."""
		pass
```

### 1.4 Trailing Whitespace

Lines must **not end with spaces or tabs**.  
Recommended: set `trim_trailing_whitespace = true` in your `.editorconfig`.

### 1.5 Encoding

All Python files use **UTF-8**.

---

## 2. Code Structure

### 2.1 Ternary Operator

The ternary operator (`x if condition else y`) is **allowed** when it fits cleanly on one line  
and improves readability. **Nested ternaries are forbidden** — they become unreadable fast.

```python
# ✓ Correct -- simple, clear ternary
label = "yes" if isActive else "no"

# ✓ Also correct -- regular if/else for complex cases
if userAge >= 18:
	status = "adult"
else:
	status = "minor"

# ✗ Wrong -- nested ternary, unreadable
result = "a" if x > 0 else ("b" if x < 0 else "c")
```

**Rule of thumb:** if the ternary fits on one line and reads like plain English, use it.  
If you have to think about it, use `if/else`.

### 2.2 No Lambda

Lambda expressions are **forbidden**. Always define a named function instead.  
Named functions are testable, can have docstrings, and appear readable in stack traces.

```python
# ✓ Correct -- named function
def double(value: int) -> int:
	"""Returns double the value."""
	return value * 2

result = list(map(double, numbers))

# ✗ Wrong -- lambda
result = list(map(lambda x: x * 2, numbers))
```

### 2.3 Prefer `match/case` over chained `if/elif`

When checking the same variable against 3 or more values, use **`match/case`** (Python 3.10+)
instead of a chain of `if/elif`. It is clearer, more readable, and easier to extend.

The threshold is **3 or more branches on the same variable**.

```python
# ✓ Correct -- match/case for 3+ branches on same variable
match command:
	case "start":
		start_service()
	case "stop":
		stop_service()
	case "restart":
		stop_service()
		start_service()
	case _:
		print(f"Unknown command: {command}")

# ✓ Also correct -- only 2 branches, if/else is fine
if isActive:
	start_service()
else:
	stop_service()

# ✗ Wrong -- 3+ elif on same variable, use match instead
if command == "start":
	start_service()
elif command == "stop":
	stop_service()
elif command == "restart":
	stop_service()
	start_service()
else:
	print(f"Unknown command: {command}")
```

`match/case` also supports pattern matching on types, tuples, and dataclasses — use it:

```python
# ✓ Correct -- pattern matching on type
match event:
	case MouseClick(x=x, y=y):
		handle_click(x, y)
	case KeyPress(key=k):
		handle_key(k)
	case _:
		pass
```

### 2.4 Maximum Nesting Depth

Maximum nesting depth is **4 levels**. Deeply nested code is a signal to extract logic  
into its own function.

Counted: `if`, `for`, `while`, `with`, `try`. The counter resets per function.

```python
# ✓ Correct -- max 4 levels
def process_orders(orders: list) -> None:
	"""Process a list of orders."""
	for order in orders:               # level 1
		if order.is_valid():           # level 2
			for item in order.items:   # level 3
				if item.in_stock():    # level 4
					item.ship()

# ✗ Wrong -- 5 levels
def process_orders(orders: list) -> None:
	for order in orders:
		if order.is_valid():
			for item in order.items:
				if item.in_stock():
					if item.weight > 0:   # level 5 -- FORBIDDEN
						item.ship()
```

Resolve deep nesting with **early returns** or **helper functions**:

```python
# ✓ Correct -- early return
def process_item(item: Item) -> None:
	"""Process a single item."""
	if not item.in_stock():
		return
	if item.weight <= 0:
		return
	item.ship()
```

---

## 3. Naming Conventions

### 3.1 Functions — `snake_case`

Function names use lowercase letters separated by underscores.

```python
# ✓ Correct
def calculate_total() -> float: ...
def send_email_notification() -> None: ...
def get_user_by_id() -> User: ...

# ✗ Wrong
def CalculateTotal() -> float: ...   # PascalCase
def sendEmail() -> None: ...         # camelCase
```

### 3.2 Classes — `CamelCase`

Class names use PascalCase (UpperCamelCase): each word starts with a capital letter, no underscores.

```python
# ✓ Correct
class UserAccount: ...
class OrderProcessor: ...
class HttpClient: ...

# ✗ Wrong
class user_account: ...    # snake_case
class userAccount: ...     # lowerCamelCase
```

### 3.3 Variables — `camelCase`

Regular variables use lowerCamelCase: first word lowercase, each subsequent word capitalized.

```python
# ✓ Correct
userName = "Sebastian"
totalPrice = 49.99
itemCount = 0
isActive = True

# ✗ Wrong
user_name = "Sebastian"    # snake_case
TotalPrice = 49.99         # PascalCase
```

Single-character variables (`i`, `j`, `x`, `n`) are **only allowed in loops and math contexts**.

```python
# ✓ OK -- loop variable
for i in range(10):
	print(i)

# ✗ Wrong -- meaningless variable outside loop
x = get_user()
```

### 3.4 Constants — `UPPER_CASE`

Constants (module-level, immutable values) use all caps with underscores.

```python
# ✓ Correct
MAX_RETRIES: int = 3
DEFAULT_TIMEOUT: float = 30.0
API_BASE_URL: str = "https://api.example.com"

# ✗ Wrong
maxRetries = 3     # camelCase
max_retries = 3    # snake_case
```

### 3.5 Filenames — `snake_case`

All Python files are named in `snake_case`.

```
# ✓ Correct
user_service.py
order_processor.py
config_loader.py

# ✗ Wrong
UserService.py
orderProcessor.py
```

### 3.6 Overview

| What | Style | Example |
|---|---|---|
| Function | `snake_case` | `get_user_by_id` |
| Class | `CamelCase` | `UserAccount` |
| Variable | `camelCase` | `totalPrice` |
| Constant | `UPPER_CASE` | `MAX_RETRIES` |
| Filename | `snake_case` | `user_service.py` |

---

## 4. Types & Documentation

### 4.1 Type Hints — Required

**All** parameters and return values must be annotated with type hints.  
`__init__` does not need a return type hint (implicitly `None`).

```python
# ✓ Correct
def calculate_discount(price: float, percent: float) -> float:
	"""Calculate the discounted price."""
	return price * (1 - percent / 100)

def get_username(userId: int) -> str | None:
	"""Return the username or None if not found."""
	...

# ✗ Wrong -- no type hints
def calculate_discount(price, percent):
	return price * (1 - percent / 100)
```

For complex types use standard typing constructs:

```python
from typing import Optional

def process_items(items: list[str]) -> dict[str, int]:
	"""Process a list of items."""
	...

def find_user(userId: int) -> Optional[str]:
	"""Find a user by ID."""
	...
```

### 4.2 Docstrings & Doxygen — Required

Every function needs **two things**:
- A short **internal docstring** (first line of the function body)
- A **Doxygen `##` comment block directly above the `def` line**

The Doxygen block is what generates the documentation (`doxypypy` + Doxygen).

**Required tags in the `##` block:**

| Tag | When |
|---|---|
| `@brief` | Always — one-line summary, on the `##` opening line |
| `@param name` | Every parameter except `self`/`cls` |
| `@return` | Whenever return type is not `None` |

**Optional tags:**

| Tag | Use for |
|---|---|
| `@note` | Extra context, caveats |
| `@warning` | Dangerous usage, side effects |
| `@throws ExcType` | Exceptions the function may raise |

```python
# ✓ Correct
## @brief Send an email notification to a recipient.
#  @param recipient Email address of the recipient.
#  @param subject   Subject line of the message.
#  @param body      Message body (plain text).
#  @param retries   Number of retry attempts on failure.
#  @return True if sent successfully, False otherwise.
def send_notification(
	recipient: str,
	subject: str,
	body: str,
	retries: int = 3,
) -> bool:
	"""Send an email notification."""
	...


# ✓ Correct — no params, no return → only @brief needed
## @brief Clear the internal user cache.
def reset_cache() -> None:
	"""Clear the cache."""
	...


# ✗ Wrong — Doxygen block missing entirely
def send_notification(recipient: str, subject: str) -> bool:
	"""Send a notification."""
	...


# ✗ Wrong — Doxygen inside the docstring, not above the def
def send_notification(recipient: str) -> bool:
	"""
	@brief Send notification.
	@param recipient The recipient.
	@return True on success.
	"""
	...
```

For classes, a `##` block with `@brief` above the `class` line is enough.
Each method still needs its own full `##` block.

```python
## @brief In-memory cache for user data, keyed by user ID.
class UserCache:
	"""In-memory user cache."""

	## @brief Retrieve a user from the cache.
	#  @param userId Numeric user identifier.
	#  @return User data dict, or None if not cached.
	def get(self, userId: int) -> dict | None:
		"""Return cached user or None."""
		return self._cache.get(userId)
```

---

## 5. Error Handling

### 5.1 No Bare `except`

A bare `except:` catches **everything**, including `KeyboardInterrupt`, `SystemExit`,  
and `MemoryError`. This is almost always a bug. Always specify the exception type.

```python
# ✓ Correct
try:
	data = load_config("config.yml")
except FileNotFoundError:
	print("Config file not found")
except yaml.YAMLError as exc:
	print(f"Invalid YAML: {exc}")

# ✗ Wrong -- catches everything including KeyboardInterrupt
try:
	data = load_config("config.yml")
except:
	print("Error")
```

### 5.2 Prefer `if/else` over Exceptions for Control Flow

Exceptions are for **exceptional situations** — not normal control flow.  
Use `if/else` wherever the case is expected.

```python
# ✓ Correct -- if/else for expected cases
def get_user(userId: int) -> dict | None:
	"""Return user data or None if not found."""
	if userId not in userDatabase:
		return None
	return userDatabase[userId]

userData = get_user(42)
if userData is None:
	print("User not found")
else:
	print(userData["name"])

# ✗ Wrong -- exception for an expected case
def get_user(userId: int) -> dict:
	if userId not in userDatabase:
		raise KeyError(f"User {userId} not found")
	return userDatabase[userId]
```

Exceptions are appropriate for:
- I/O errors (file unreadable, network failure)
- Invalid program states that should never occur
- Errors from external libraries

---

## 6. Global Variables

Global variables should be kept to an **absolute minimum**.  
They make testing, debugging, and reasoning about code harder.

```python
# ✗ Bad -- global state
userCache = {}

def get_user(userId: int) -> dict:
	"""Return user."""
	if userId in userCache:
		return userCache[userId]
	...

# ✓ Better -- encapsulate state in a class
class UserCache:
	"""Cache for user data."""

	def __init__(self) -> None:
		self._cache: dict[int, dict] = {}

	def get(self, userId: int) -> dict | None:
		"""Return cached user or None."""
		return self._cache.get(userId)
```

Module-level constants (`UPPER_CASE`) are fine — they are immutable and clearly recognizable.

---

## 7. Configuration

All config values that vary between environments (URLs, timeouts, credentials, paths,  
feature flags) go **exclusively in a config file**. Never hardcode them.

### 7.1 Format

Allowed formats: **YAML** (`.yml`) or **JSON** (`.json`).  
YAML is preferred for readability.

```yaml
# config.yml
database:
  host: "localhost"
  port: 5432
  name: "myapp"

api:
  base_url: "https://api.example.com"
  timeout: 30
  max_retries: 3

feature_flags:
  new_dashboard: true
  beta_mode: false
```

### 7.2 Loading

```python
# config_loader.py
import yaml
from pathlib import Path

CONFIG_PATH: str = "config.yml"


def load_config(path: str = CONFIG_PATH) -> dict:
	"""
	Load configuration from a YAML file.

	Args:
		path: Path to the config file.

	Returns:
		Dictionary with all configuration values.
	"""
	configFile = Path(path)
	if not configFile.exists():
		raise FileNotFoundError(f"Config file not found: {path}")

	with open(configFile, encoding="utf-8") as f:
		return yaml.safe_load(f)
```

### 7.3 Secrets

Passwords, API keys, and other secrets must **never** be in the config file  
and absolutely never committed to the repository. Use environment variables instead.

```python
import os

API_KEY: str | None = os.getenv("MY_API_KEY")

if API_KEY is None:
	raise EnvironmentError("MY_API_KEY is not set")
```

---

## 8. File Structure

### 8.1 Layout of a Python File

Every file follows this order:

```
1. Module docstring
2. Imports (stdlib → third-party → local, each group separated by a blank line)
3. Constants
4. Classes
5. Functions
6. if __name__ == "__main__": block (if needed)
```

```python
"""
user_service.py -- Manages user data and authentication.
"""

import os
from pathlib import Path

import yaml

from myapp.models import User
from myapp.config_loader import load_config

MAX_LOGIN_ATTEMPTS: int = 5
SESSION_TIMEOUT: int = 3600


class UserService:
	"""Provides user-related operations."""

	...


def create_guest_user() -> User:
	"""Create a temporary guest user."""
	...


if __name__ == "__main__":
	service = UserService()
```

---

## 9. Quick Reference

| Rule | Value |
|---|---|
| Indentation | Tabs (1 tab = 4 spaces) |
| Line length | Warning at 120 chars |
| Blank lines | 2 between top-level definitions |
| Trailing whitespace | Forbidden |
| Ternary | Allowed (no nested ternary) |
| Lambda | Forbidden |
| Max nesting | 4 levels |
| Function naming | `snake_case` |
| Class naming | `CamelCase` |
| Variable naming | `camelCase` |
| Constant naming | `UPPER_CASE` |
| Filename | `snake_case` |
| Docstrings | Required |
| Type hints | Required |
| Bare `except` | Forbidden |
| Exceptions | Only when truly necessary |
| Globals | Keep to absolute minimum |
| Config | Always in `.yml` or `.json` |
