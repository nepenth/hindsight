#!/usr/bin/env python3
"""
Documentation Example Tester

Uses an LLM to extract code examples from documentation and test them.
This ensures documentation stays in sync with the actual codebase.

Usage:
    python scripts/test-doc-examples.py

Environment variables:
    OPENAI_API_KEY: Required for LLM calls
    HINDSIGHT_API_URL: URL of running Hindsight server (default: http://localhost:8888)
"""

import os
import re
import sys
import site
import json
import glob
import subprocess
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional
import threading

from openai import OpenAI

# Thread-safe print lock
print_lock = threading.Lock()


def discover_and_install_dependencies(repo_root: str) -> dict:
    """Install required dependencies for doc testing."""
    print("\n=== Installing dependencies ===")

    results = {
        "local_packages": [],
        "cli_available": False
    }

    # Core local packages (order matters - dependencies first)
    local_python_packages = [
        ("hindsight-clients/python", "hindsight_client"),
        ("hindsight-integrations/litellm", "hindsight_litellm"),
        ("hindsight-integrations/openai", "hindsight_openai"),
    ]

    # Check which packages are already installed
    print("\nChecking installed Python packages...")
    installed_packages = set()
    for pkg_path, pkg_name in local_python_packages:
        try:
            result = subprocess.run(
                [sys.executable, "-c", f"import {pkg_name}"],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"  {pkg_name}: already installed")
                installed_packages.add(pkg_name)
                results["local_packages"].append(pkg_name)
        except Exception:
            pass

    # Install missing local Python packages
    packages_to_install = [(p, n) for p, n in local_python_packages if n not in installed_packages]
    if packages_to_install:
        print("\nInstalling missing Python packages...")
        for pkg_path, pkg_name in packages_to_install:
            full_path = os.path.join(repo_root, pkg_path)
            if os.path.exists(full_path):
                try:
                    result = subprocess.run(
                        ["uv", "pip", "install", full_path],
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    if result.returncode == 0:
                        print(f"  Installed {pkg_name}")
                        results["local_packages"].append(pkg_name)
                    else:
                        print(f"  Failed to install {pkg_name}: {result.stderr[:200]}")
                except Exception as e:
                    print(f"  Failed to install {pkg_name}: {e}")
    else:
        print("  All packages already installed")

    # Build TypeScript client and set up symlink
    ts_client_path = os.path.join(repo_root, "hindsight-clients/typescript")
    if os.path.exists(ts_client_path):
        print("\nBuilding TypeScript client...")
        try:
            # Install npm dependencies
            subprocess.run(["npm", "ci"], cwd=ts_client_path, capture_output=True, timeout=120)
            # Build
            subprocess.run(["npm", "run", "build"], cwd=ts_client_path, capture_output=True, timeout=60)
            # Create symlink in /tmp for ESM module resolution
            os.makedirs("/tmp/node_modules/@vectorize-io", exist_ok=True)
            symlink_path = "/tmp/node_modules/@vectorize-io/hindsight-client"
            if os.path.islink(symlink_path):
                os.unlink(symlink_path)
            os.symlink(ts_client_path, symlink_path)
            print("  TypeScript client built and symlinked")
        except Exception as e:
            print(f"  Failed to build TypeScript client: {e}")

    # Try to build hindsight CLI if Rust is available
    cli_path = os.path.join(repo_root, "hindsight-cli")
    if os.path.exists(cli_path):
        print("\nChecking for Rust toolchain...")
        try:
            cargo_result = subprocess.run(["cargo", "--version"], capture_output=True, timeout=5)
            if cargo_result.returncode == 0:
                print("  Rust found, building hindsight CLI...")
                build_result = subprocess.run(
                    ["cargo", "build", "--release"],
                    cwd=cli_path,
                    capture_output=True,
                    timeout=300
                )
                if build_result.returncode == 0:
                    # Try to install to PATH
                    cli_binary = os.path.join(cli_path, "target/release/hindsight")
                    if os.path.exists(cli_binary):
                        # Copy to /usr/local/bin or ~/.local/bin
                        local_bin = os.path.expanduser("~/.local/bin")
                        os.makedirs(local_bin, exist_ok=True)
                        import shutil
                        shutil.copy2(cli_binary, os.path.join(local_bin, "hindsight"))
                        os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"
                        results["cli_available"] = True
                        print("  CLI built and installed")
                else:
                    print(f"  CLI build failed")
            else:
                print("  Rust not available, skipping CLI build")
        except FileNotFoundError:
            print("  Rust not installed, skipping CLI build")
        except Exception as e:
            print(f"  CLI build error: {e}")

    # Check if CLI is available (might be pre-installed)
    if not results["cli_available"]:
        try:
            result = subprocess.run(["hindsight", "--version"], capture_output=True, timeout=5)
            results["cli_available"] = result.returncode == 0
            if results["cli_available"]:
                print("  CLI already available in PATH")
        except Exception:
            pass

    print("\n=== Dependency installation complete ===\n")
    return results


@dataclass
class CodeExample:
    """Represents a code example extracted from documentation."""
    file_path: str
    language: str
    code: str
    context: str  # Surrounding text for context
    line_number: int


@dataclass
class TestResult:
    """Result of testing a code example."""
    example: CodeExample
    success: bool
    output: str
    error: Optional[str] = None


@dataclass
class TestReport:
    """Final test report."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[TestResult] = field(default_factory=list)
    created_banks: list[str] = field(default_factory=list)  # Track banks for cleanup

    def add_result(self, result: TestResult):
        self.total += 1
        self.results.append(result)
        if result.success:
            self.passed += 1
        elif result.error and "SKIPPED" in result.error:
            self.skipped += 1
        else:
            self.failed += 1

    def add_bank(self, bank_id: str):
        """Track a bank that was created during testing."""
        if bank_id not in self.created_banks:
            self.created_banks.append(bank_id)


def find_markdown_files(repo_root: str) -> list[str]:
    """Find all markdown files in the repository, excluding auto-generated docs."""
    md_files = []
    # Directories to skip (auto-generated docs, dependencies, etc.)
    skip_patterns = [
        "node_modules",
        ".git",
        "venv",
        "__pycache__",
        "hindsight_client_api/docs",  # Auto-generated OpenAPI docs
        "hindsight-clients/typescript/docs",  # Auto-generated TS docs
        "target/",  # Rust build artifacts
        "dist/",  # Build outputs
    ]
    for pattern in ["*.md", "**/*.md"]:
        for f in glob.glob(os.path.join(repo_root, pattern), recursive=True):
            # Skip symlinks to avoid circular references
            if os.path.islink(f):
                continue
            # Check if any parent directory is a symlink (circular reference protection)
            try:
                real_path = os.path.realpath(f)
                if not real_path.startswith(os.path.realpath(repo_root)):
                    continue
            except Exception:
                continue
            if any(skip in f for skip in skip_patterns):
                continue
            md_files.append(f)
    return sorted(set(md_files))


def is_obviously_not_testable(code: str, language: str) -> tuple[bool, str]:
    """Pre-filter obviously non-testable examples to avoid LLM calls."""
    code_lower = code.lower().strip()

    if language in ["bash", "sh"]:
        # Installation commands
        if code_lower.startswith(("pip install", "npm install", "yarn add", "uv pip install", "cargo install")):
            return True, "Package installation command"
        if code_lower.startswith(("curl ", "wget ")) and ("install" in code_lower or "get-" in code_lower):
            return True, "Installation script"

        # Docker/container commands
        if "docker " in code_lower or "docker-compose" in code_lower:
            return True, "Docker command"
        if code_lower.startswith("helm "):
            return True, "Helm command"

        # Build/test commands
        if code_lower.startswith(("cargo build", "cargo test")):
            return True, "Cargo build/test command"
        if "pytest" in code_lower or "uv run pytest" in code_lower:
            return True, "Test suite command"

        # Git commands
        if code_lower.startswith("git clone"):
            return True, "Git clone command"

        # Development scripts that won't exist in CI
        if "./scripts/" in code_lower:
            return True, "Development script"

        # npm/yarn dev commands (not install)
        if any(x in code_lower for x in ["npm run dev", "npm run start", "npm run build", "yarn dev", "yarn start"]):
            return True, "Development server command"
        if "npm run deploy" in code_lower or "npm deploy" in code_lower:
            return True, "Deployment command"

        # cd to relative project directories (won't work from temp)
        if code_lower.startswith("cd ") and not code_lower.startswith("cd /"):
            # Allow cd to temp directories
            if not any(x in code_lower for x in ["/tmp", "$tmp", "${tmp"]):
                return True, "Relative directory change"

    # Environment setup
    if code_lower.startswith("export ") and "=" in code_lower:
        return True, "Environment variable export"

    # Config file contents (YAML, TOML, JSON without code)
    if language in ["yaml", "toml", "json", "env"]:
        return True, "Configuration file content"

    # Very short snippets (likely fragments)
    if len(code.strip()) < 20:
        return True, "Code fragment too short"

    return False, ""


def extract_code_blocks(file_path: str) -> list[CodeExample]:
    """Extract code blocks from a markdown file."""
    with open(file_path, "r") as f:
        content = f.read()

    examples = []
    # Match fenced code blocks with language identifier
    pattern = r"```(\w+)\n(.*?)```"

    for match in re.finditer(pattern, content, re.DOTALL):
        language = match.group(1).lower()
        code = match.group(2).strip()

        # Calculate line number
        line_number = content[:match.start()].count('\n') + 1

        # Only include testable languages
        if language not in ["python", "typescript", "javascript", "bash", "sh"]:
            continue

        # Get surrounding context (reduced from 200 to 150 chars for efficiency)
        start = max(0, match.start() - 150)
        end = min(len(content), match.end() + 150)
        context = content[start:end]

        examples.append(CodeExample(
            file_path=file_path,
            language=language,
            code=code,
            context=context,
            line_number=line_number
        ))

    return examples


def analyze_example_with_llm(client: OpenAI, example: CodeExample, hindsight_url: str, repo_root: str, cli_available: bool = True, model: str = "gpt-4o") -> dict:
    """Use LLM to analyze a code example and determine how to test it."""

    # Build language-specific rules (only include relevant ones)
    lang_rules = ""
    if example.language == "python":
        lang_rules = f"""
PYTHON RULES:
- Import: `from hindsight_client import Hindsight`
- Client is SYNCHRONOUS - NO async/await, NO asyncio.run()
- Initialize: `client = Hindsight(base_url="{hindsight_url}")`
- retain(bank_id, content, context=None, document_id=None)
- retain_batch(bank_id, items=[{{"content": "..."}}, ...]) - NOTE: 'items' not 'contents'
- recall(bank_id, query, budget="mid") → .results[].text
- reflect(bank_id, query) → .text
- create_bank(bank_id, name=None, background=None) - EXISTS in SDK
- client.close() for cleanup
- NO delete_bank() method - use: requests.delete(f"{hindsight_url}/v1/default/banks/{{bank_id}}")
- Wrap in try/finally, print "TEST PASSED" on success
- Add ALL necessary imports (uuid, requests, os, etc.)"""

    elif example.language in ["typescript", "javascript"]:
        lang_rules = f"""
JAVASCRIPT RULES (CRITICAL - generate PURE JS, not TypeScript):
- NO type annotations (: string, : Promise<void>, etc.) - causes SyntaxError
- Import: `import {{ HindsightClient }} from '@vectorize-io/hindsight-client';`
- Initialize: `const client = new HindsightClient({{ baseUrl: '{hindsight_url}' }});`
- retain(bankId, content) - positional args
- retainBatch(bankId, items, options) - positional, NOT {{bankId, contents}}
- recall(bankId, query) → response.results[].text
- reflect(bankId, query) → response.text
- createBank(bankId, options) - EXISTS in SDK
- NO client.close() method
- Cleanup: `await fetch(`{hindsight_url}/v1/default/banks/${{bankId}}`, {{ method: 'DELETE' }});`
- Use crypto.randomUUID() for UUIDs, native fetch() for HTTP
- NO external packages (node-fetch, uuid, axios)"""

    elif example.language in ["bash", "sh"]:
        cli_status = "AVAILABLE" if cli_available else "NOT INSTALLED - mark as NOT testable"
        lang_rules = f"""
CLI RULES (status: {cli_status}):
- Memory ops: `hindsight memory retain|recall|reflect <bank_id> "content"`
- Bank ops: `hindsight bank list|disposition|stats|name|background|delete`
- NO 'hindsight bank create' - banks auto-create on first use
- NO 'hindsight bank profile' - use 'disposition'
- NO 'hindsight retain/recall' - must include 'memory' subcommand
- For file tests: create temp file first with `echo "content" > /tmp/test.txt`"""

    prompt = f"""Analyze and test this documentation code example.

File: {example.file_path}:{example.line_number}
Language: {example.language}
Hindsight API: {hindsight_url} (already running)
Repo: {repo_root}

Context: {example.context}

Code:
```{example.language}
{example.code}
```

SKIP if: Docker/server setup, class/function definition without execution, helm commands.

PLACEHOLDERS - Replace with real values:
- <bank_id>/my-bank → unique ID like "doc-test-<uuid>"
- <query>/<content> → realistic test strings
- api_key="sk-..." → os.environ["OPENAI_API_KEY"]
- File paths → create temp files first
{lang_rules}

Respond JSON: {{"testable": bool, "reason": "...", "language": "python|typescript|bash", "test_script": "..." or null, "cleanup_script": "..." or null}}"""

    # Reasoning models (o1, o3, etc.) don't support temperature parameter
    is_reasoning_model = model.startswith(("o1", "o3"))

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    if is_reasoning_model:
        kwargs["max_completion_tokens"] = 16000
    else:
        kwargs["temperature"] = 0

    response = client.chat.completions.create(**kwargs)

    return json.loads(response.choices[0].message.content)


def run_python_test(script: str, timeout: int = 60) -> tuple[bool, str, Optional[str]]:
    """Run a Python test script."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        f.flush()

        try:
            # Ensure the subprocess can find installed packages by adding site-packages to PYTHONPATH
            site_packages = site.getsitepackages()
            current_pythonpath = os.environ.get("PYTHONPATH", "")
            new_pythonpath = ":".join(site_packages + ([current_pythonpath] if current_pythonpath else []))

            result = subprocess.run(
                [sys.executable, f.name],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": new_pythonpath}
            )
            output = result.stdout + result.stderr
            # Check for "TEST PASSED" in output as primary success indicator
            # This handles cases where exit code might be non-zero due to warnings
            if "TEST PASSED" in output:
                return True, output, None
            success = result.returncode == 0
            error = None if success else f"Exit code: {result.returncode}\n{result.stderr}"
            return success, output, error
        except subprocess.TimeoutExpired:
            return False, "", f"Test timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)
        finally:
            os.unlink(f.name)


def run_typescript_test(script: str, timeout: int = 60) -> tuple[bool, str, Optional[str]]:
    """Run a TypeScript/JavaScript test script."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False, dir='/tmp') as f:
        f.write(script)
        f.flush()

        try:
            # Set NODE_PATH to find packages in /tmp/node_modules (created by CI)
            env = {**os.environ}
            node_path = env.get("NODE_PATH", "")
            env["NODE_PATH"] = f"/tmp/node_modules:{node_path}" if node_path else "/tmp/node_modules"

            result = subprocess.run(
                ["node", f.name],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd="/tmp"  # Run from /tmp so relative imports work
            )
            success = result.returncode == 0
            output = result.stdout + result.stderr
            error = None if success else f"Exit code: {result.returncode}\n{result.stderr}"
            return success, output, error
        except subprocess.TimeoutExpired:
            return False, "", f"Test timed out after {timeout}s"
        except FileNotFoundError:
            return False, "", "Node.js not found"
        except Exception as e:
            return False, "", str(e)
        finally:
            os.unlink(f.name)


def run_bash_test(script: str, timeout: int = 60) -> tuple[bool, str, Optional[str]]:
    """Run a bash test script."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("#!/bin/bash\nset -e\n" + script)
        f.flush()
        os.chmod(f.name, 0o755)

        try:
            result = subprocess.run(
                ["bash", f.name],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            success = result.returncode == 0
            output = result.stdout + result.stderr
            error = None if success else f"Exit code: {result.returncode}\n{result.stderr}"
            return success, output, error
        except subprocess.TimeoutExpired:
            return False, "", f"Test timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)
        finally:
            os.unlink(f.name)


def safe_print(*args, **kwargs):
    """Thread-safe print."""
    with print_lock:
        print(*args, **kwargs)
        sys.stdout.flush()


def test_example(openai_client: OpenAI, example: CodeExample, hindsight_url: str, repo_root: str, cli_available: bool = True, debug: bool = False, model: str = "gpt-4o") -> TestResult:
    """Test a single code example."""
    safe_print(f"  Testing {example.file_path}:{example.line_number} ({example.language})")

    # Pre-filter obviously non-testable examples (saves LLM calls)
    skip, reason = is_obviously_not_testable(example.code, example.language)
    if skip:
        safe_print(f"    SKIPPED (pre-filter): {reason}")
        return TestResult(
            example=example,
            success=True,
            output="",
            error=f"SKIPPED: {reason}"
        )

    # CLI not available - skip bash examples
    if not cli_available and example.language in ["bash", "sh"] and "hindsight" in example.code.lower():
        safe_print(f"    SKIPPED: CLI not installed")
        return TestResult(
            example=example,
            success=True,
            output="",
            error="SKIPPED: CLI not installed"
        )

    try:
        # Analyze with LLM
        analysis = analyze_example_with_llm(openai_client, example, hindsight_url, repo_root, cli_available, model=model)

        if debug and analysis.get("test_script"):
            safe_print(f"    [DEBUG] Generated script:\n{analysis.get('test_script')}")

        if not analysis.get("testable", False):
            safe_print(f"    SKIPPED: {analysis.get('reason', 'Not testable')}")
            return TestResult(
                example=example,
                success=True,
                output="",
                error=f"SKIPPED: {analysis.get('reason', 'Not testable')}"
            )

        test_script = analysis.get("test_script")
        if not test_script:
            safe_print(f"    SKIPPED: No test script generated")
            return TestResult(
                example=example,
                success=True,
                output="",
                error="SKIPPED: No test script generated"
            )

        # Run the test based on language
        lang = analysis.get("language", example.language)
        if lang == "python":
            success, output, error = run_python_test(test_script)
        elif lang in ["typescript", "javascript"]:
            success, output, error = run_typescript_test(test_script)
        elif lang in ["bash", "sh"]:
            success, output, error = run_bash_test(test_script)
        else:
            safe_print(f"    SKIPPED: Unsupported language {lang}")
            return TestResult(
                example=example,
                success=True,
                output="",
                error=f"SKIPPED: Unsupported language {lang}"
            )

        # Run cleanup if provided
        cleanup = analysis.get("cleanup_script")
        if cleanup and lang == "python":
            run_python_test(cleanup, timeout=30)

        if success:
            safe_print(f"    PASSED")
        else:
            safe_print(f"    FAILED: {error[:200] if error else 'Unknown error'}")

        return TestResult(
            example=example,
            success=success,
            output=output,
            error=error
        )

    except Exception as e:
        error_msg = f"Exception: {str(e)}\n{traceback.format_exc()}"
        safe_print(f"    ERROR: {error_msg[:200]}")
        return TestResult(
            example=example,
            success=False,
            output="",
            error=error_msg
        )


def cleanup_test_banks(hindsight_url: str, report: TestReport):
    """Clean up any banks created during testing."""
    import urllib.request
    import urllib.error

    # Also search for any doc-test-* banks that might have been left behind
    try:
        req = urllib.request.Request(f"{hindsight_url}/v1/default/banks")
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            for bank in data.get("banks", []):
                bank_id = bank.get("bank_id", "")
                if bank_id.startswith("doc-test-"):
                    report.add_bank(bank_id)
    except Exception:
        pass  # Ignore errors listing banks

    if not report.created_banks:
        return

    print(f"\nCleaning up {len(report.created_banks)} test banks...")
    for bank_id in report.created_banks:
        try:
            req = urllib.request.Request(
                f"{hindsight_url}/v1/default/banks/{bank_id}",
                method="DELETE"
            )
            urllib.request.urlopen(req, timeout=10)
            print(f"  Deleted: {bank_id}")
        except Exception as e:
            print(f"  Failed to delete {bank_id}: {e}")


def print_report(report: TestReport):
    """Print the final test report."""
    print("\n" + "=" * 70)
    print("DOCUMENTATION EXAMPLE TEST REPORT")
    print("=" * 70)
    print(f"\nTotal examples: {report.total}")
    print(f"  Passed:  {report.passed}")
    print(f"  Failed:  {report.failed}")
    print(f"  Skipped: {report.skipped}")

    if report.failed > 0:
        print("\n" + "-" * 70)
        print("FAILURES:")
        print("-" * 70)

        for result in report.results:
            if not result.success and result.error and "SKIPPED" not in result.error:
                print(f"\n{result.example.file_path}:{result.example.line_number}")
                print(f"Language: {result.example.language}")
                print(f"Code snippet:")
                print("  " + result.example.code[:200].replace("\n", "\n  ") + "...")
                print(f"Error: {result.error}")

    print("\n" + "=" * 70)

    if report.failed > 0:
        print("RESULT: FAILED")
    else:
        print("RESULT: PASSED")
    print("=" * 70)


def write_github_summary(report: TestReport, output_path: str, openai_client: OpenAI = None, model: str = "gpt-4o"):
    """Write a GitHub Actions compatible markdown summary."""
    lines = []

    # Header
    status_emoji = "❌" if report.failed > 0 else "✅"
    lines.append(f"# {status_emoji} Documentation Examples Test Report")
    lines.append("")

    # Summary stats
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total | {report.total} |")
    lines.append(f"| ✅ Passed | {report.passed} |")
    lines.append(f"| ❌ Failed | {report.failed} |")
    lines.append(f"| ⏭️ Skipped | {report.skipped} |")
    lines.append("")

    # If there are failures, generate the list programmatically (NOT via LLM to avoid hallucinations)
    if report.failed > 0:
        # Collect actual failures from results
        failures_by_file = {}
        failure_errors = []
        for result in report.results:
            if not result.success and result.error and "SKIPPED" not in result.error:
                file_path = result.example.file_path
                if "/hindsight/" in file_path:
                    file_path = file_path.split("/hindsight/", 1)[-1]

                if file_path not in failures_by_file:
                    failures_by_file[file_path] = []

                # Extract brief error description
                error_brief = result.error[:150].replace("\n", " ") if result.error else "Unknown error"
                failures_by_file[file_path].append({
                    "line": result.example.line_number,
                    "language": result.example.language,
                    "error": error_brief
                })
                failure_errors.append(error_brief)

        # Generate failure list programmatically
        lines.append("## Failed Tests")
        lines.append("")
        for file_path in sorted(failures_by_file.keys()):
            lines.append(f"### `{file_path}`")
            for failure in sorted(failures_by_file[file_path], key=lambda x: x["line"]):
                lines.append(f"- **Line {failure['line']}** ({failure['language']}): {failure['error']}")
            lines.append("")

        # Use LLM only to categorize errors (not to list them)
        if openai_client and failure_errors:
            error_list = "\n".join(f"- {e}" for e in failure_errors[:100])  # Limit to avoid token overflow
            prompt = f"""Categorize these {len(failure_errors)} error messages into groups.

Errors:
{error_list}

Output a markdown section with categories like:
## Categories
- **CLI commands don't exist**: X
- **Wrong attribute names in Python**: X
- **TypeScript errors**: X
etc.

Just output the categories section, nothing else. Be brief."""

            try:
                # Reasoning models (o1, o3, etc.) don't support temperature/max_tokens
                is_reasoning_model = model.startswith(("o1", "o3"))

                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if is_reasoning_model:
                    kwargs["max_completion_tokens"] = 1000
                else:
                    kwargs["temperature"] = 0
                    kwargs["max_tokens"] = 1000

                response = openai_client.chat.completions.create(**kwargs)
                categories = response.choices[0].message.content
                lines.append(categories)
            except Exception as e:
                lines.append(f"## Categories")
                lines.append(f"*Categorization failed: {e}*")

    # Write to file
    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def main():
    # Ensure unbuffered output
    sys.stdout.reconfigure(line_buffering=True)

    # Check for required environment variables
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable is required")
        sys.exit(1)

    hindsight_url = os.environ.get("HINDSIGHT_API_URL", "http://localhost:8888")

    # Find repo root (handle both script execution and exec())
    if '__file__' in globals():
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    else:
        # Fallback: use current directory or REPO_ROOT env var
        repo_root = os.environ.get("REPO_ROOT", os.getcwd())
    print(f"Repository root: {repo_root}")

    # Discover and install dependencies
    dep_results = discover_and_install_dependencies(repo_root)
    cli_available = dep_results["cli_available"]

    # Check if Hindsight is running
    try:
        import urllib.request
        urllib.request.urlopen(f"{hindsight_url}/health", timeout=5)
        print(f"Hindsight API is running at {hindsight_url}")
    except Exception as e:
        print(f"WARNING: Could not connect to Hindsight at {hindsight_url}: {e}")
        print("Some tests may fail if they require a running server")

    if not cli_available:
        print("WARNING: hindsight CLI not available - CLI examples will be skipped")

    # Initialize OpenAI client
    client = OpenAI(api_key=openai_api_key)

    # Model configuration - use DOC_TEST_MODEL env var or default to gpt-4o
    model = os.environ.get("DOC_TEST_MODEL", "gpt-4o")
    print(f"Using model: {model}")

    # Find all markdown files
    md_files = find_markdown_files(repo_root)
    print(f"\nFound {len(md_files)} markdown files")

    # Extract all code examples
    all_examples = []
    for md_file in md_files:
        examples = extract_code_blocks(md_file)
        if examples:
            print(f"  {md_file}: {len(examples)} code blocks")
            all_examples.extend(examples)

    print(f"\nTotal code examples to test: {len(all_examples)}")

    # Test examples in parallel
    report = TestReport()
    debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    max_workers = int(os.environ.get("MAX_WORKERS", "8"))  # Default 8 parallel workers

    print(f"Running tests with {max_workers} parallel workers...")

    def run_test(args):
        idx, example = args
        safe_print(f"\n[{idx}/{len(all_examples)}] Testing example...")
        return test_example(client, example, hindsight_url, repo_root, cli_available=cli_available, debug=debug, model=model)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(run_test, (i, ex)): i for i, ex in enumerate(all_examples, 1)}

        # Collect results as they complete
        for future in as_completed(futures):
            result = future.result()
            report.add_result(result)

    # Clean up any test banks (runs even if tests failed)
    cleanup_test_banks(hindsight_url, report)

    # Print report
    print_report(report)

    # Write summary to file for CI (pass OpenAI client for LLM-powered summary)
    summary_path = "/tmp/doc-test-summary.md"
    write_github_summary(report, summary_path, openai_client=client, model=model)
    print(f"Summary written to {summary_path}")

    # Exit with appropriate code
    sys.exit(1 if report.failed > 0 else 0)


if __name__ == "__main__":
    main()
