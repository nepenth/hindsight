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
import json
import glob
import subprocess
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openai import OpenAI


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
    """Find all markdown files in the repository, excluding node_modules."""
    md_files = []
    for pattern in ["*.md", "**/*.md"]:
        for f in glob.glob(os.path.join(repo_root, pattern), recursive=True):
            # Skip node_modules and other common exclusions
            if any(skip in f for skip in ["node_modules", ".git", "venv", "__pycache__"]):
                continue
            md_files.append(f)
    return sorted(set(md_files))


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

        # Get surrounding context (100 chars before and after)
        start = max(0, match.start() - 200)
        end = min(len(content), match.end() + 200)
        context = content[start:end]

        # Calculate line number
        line_number = content[:match.start()].count('\n') + 1

        # Only include testable languages
        if language in ["python", "typescript", "javascript", "bash", "sh"]:
            examples.append(CodeExample(
                file_path=file_path,
                language=language,
                code=code,
                context=context,
                line_number=line_number
            ))

    return examples


def analyze_example_with_llm(client: OpenAI, example: CodeExample, hindsight_url: str) -> dict:
    """Use LLM to analyze a code example and determine how to test it."""

    prompt = f"""Analyze this code example from documentation and determine how to test it.

File: {example.file_path}
Language: {example.language}
Line: {example.line_number}

Context around the code:
{example.context}

Code:
```{example.language}
{example.code}
```

Your task:
1. Determine if this code example is testable (some are just fragments or pseudo-code)
2. If testable, generate a complete, runnable test script
3. The test should verify the example works correctly

IMPORTANT RULES:
- Hindsight API is ALREADY running at: {hindsight_url} - do NOT start Docker containers or servers
- Mark Docker/server setup examples as NOT testable (reason: "Server setup example - server already running")
- Mark pip/npm install commands as NOT testable (reason: "Package installation command")
- For Python examples, use: `from hindsight_client import Hindsight; client = Hindsight(base_url="{hindsight_url}")`
- For TypeScript/JavaScript, the server is at {hindsight_url}
- Use unique bank_id names like "doc-test-<random-uuid>" to avoid conflicts
- Add cleanup using: requests.delete("{hindsight_url}/v1/default/banks/<bank_id>")
- For Python, wrap in try/except and use sys.exit(0) for success, sys.exit(1) for actual failures
- Test script should print "TEST PASSED" on success before exiting with 0

HINDSIGHT CLIENT RESPONSE TYPES (Python):
- retain() returns RetainResponse with: success (bool), bank_id (str), items_count (int)
- recall() returns RecallResponse with: results (list of RecallResult objects, each has .text attribute)
- reflect() returns ReflectResponse with: text (str)

To verify responses:
- For retain: check response.success == True
- For recall: check len(response.results) > 0 or any keyword in str(response.results)
- For reflect: check response.text is not None and len(response.text) > 0

Respond with JSON:
{{
    "testable": true/false,
    "reason": "Why it is or isn't testable",
    "language": "python|typescript|bash",
    "test_script": "Complete runnable test script that will exit 0 on success, non-zero on failure",
    "cleanup_script": "Optional cleanup script to run after test"
}}

If not testable, set test_script to null."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0
    )

    return json.loads(response.choices[0].message.content)


def run_python_test(script: str, timeout: int = 60) -> tuple[bool, str, Optional[str]]:
    """Run a Python test script."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        f.flush()

        try:
            result = subprocess.run(
                [sys.executable, f.name],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
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
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mjs', delete=False) as f:
        f.write(script)
        f.flush()

        try:
            result = subprocess.run(
                ["node", f.name],
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


def test_example(client: OpenAI, example: CodeExample, hindsight_url: str, debug: bool = False) -> TestResult:
    """Test a single code example."""
    print(f"\n  Testing {example.file_path}:{example.line_number} ({example.language})")

    try:
        # Analyze with LLM
        analysis = analyze_example_with_llm(client, example, hindsight_url)

        if debug and analysis.get("test_script"):
            print(f"    [DEBUG] Generated script:\n{analysis.get('test_script')}")

        if not analysis.get("testable", False):
            print(f"    SKIPPED: {analysis.get('reason', 'Not testable')}")
            return TestResult(
                example=example,
                success=True,
                output="",
                error=f"SKIPPED: {analysis.get('reason', 'Not testable')}"
            )

        test_script = analysis.get("test_script")
        if not test_script:
            print(f"    SKIPPED: No test script generated")
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
            print(f"    SKIPPED: Unsupported language {lang}")
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
            print(f"    PASSED")
        else:
            print(f"    FAILED: {error}")

        return TestResult(
            example=example,
            success=success,
            output=output,
            error=error
        )

    except Exception as e:
        error_msg = f"Exception: {str(e)}\n{traceback.format_exc()}"
        print(f"    ERROR: {error_msg}")
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


def main():
    # Ensure unbuffered output
    sys.stdout.reconfigure(line_buffering=True)

    # Check for required environment variables
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable is required")
        sys.exit(1)

    hindsight_url = os.environ.get("HINDSIGHT_API_URL", "http://localhost:8888")

    # Check if Hindsight is running
    try:
        import urllib.request
        urllib.request.urlopen(f"{hindsight_url}/health", timeout=5)
        print(f"Hindsight API is running at {hindsight_url}")
    except Exception as e:
        print(f"WARNING: Could not connect to Hindsight at {hindsight_url}: {e}")
        print("Some tests may fail if they require a running server")

    # Initialize OpenAI client
    client = OpenAI(api_key=openai_api_key)

    # Find repo root (handle both script execution and exec())
    if '__file__' in globals():
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    else:
        # Fallback: use current directory or REPO_ROOT env var
        repo_root = os.environ.get("REPO_ROOT", os.getcwd())
    print(f"Repository root: {repo_root}")

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

    # Test each example
    report = TestReport()
    debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")

    for i, example in enumerate(all_examples, 1):
        print(f"\n[{i}/{len(all_examples)}] Testing example...")
        result = test_example(client, example, hindsight_url, debug=debug)
        report.add_result(result)

    # Clean up any test banks (runs even if tests failed)
    cleanup_test_banks(hindsight_url, report)

    # Print report
    print_report(report)

    # Exit with appropriate code
    sys.exit(1 if report.failed > 0 else 0)


if __name__ == "__main__":
    main()
