"""Privacy and sanitization regression test.

Guarantees that no personal identifiers, private hostnames, local paths,
or sensitive personal names (Friend, Friend, Sam, personal companion references)
leak into tracked repository files as development continues.
"""
from __future__ import annotations
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Binary / asset extensions to skip reading as text
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp',
    '.woff', '.woff2', '.ttf', '.eot',
    '.onnx', '.pyc', '.zip', '.tar', '.gz', '.whl'
}

# Forbidden regex patterns (case-insensitive unless noted)
FORBIDDEN_PATTERNS = [
    (re.compile(r'\bzach\b', re.IGNORECASE), "Personal name: Friend"),
    (re.compile(r'\bjoyner\b', re.IGNORECASE), "Personal name: Friend"),
    (re.compile(r'\bsam\b', re.IGNORECASE), "Personal name: Sam"),
    (re.compile(r'\b(tamanitomo-host|tamanitomo-host|tamanitomo-host|tamanitomo-host)\b', re.IGNORECASE), "Private hostname"),
    (re.compile(r'100\.99\.72\.3'), "Private network IP"),
    (re.compile(r'example', re.IGNORECASE), "Private domain: example"),
    (re.compile(r'/home/user', re.IGNORECASE), "Private home path: /home/user"),
]

# Pattern for Gemma: allowed only when referencing Google Gemma AI model / family
NOVA_PATTERN = re.compile(r'\bgemma\b', re.IGNORECASE)
ALLOWED_NOVA_SUBSTRINGS = [
    'google/gemma',
    "'gemma' in nl: family = 'gemma'",
]

def scan_text_for_leaks(text: str, filename: str = '') -> list[str]:
    """Scan text content and return any violation strings with line numbers."""
    violations = []
    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        # 1. Check general forbidden patterns
        for pattern, label in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                violations.append(f"{filename}:{lineno} [{label}] -> {line.strip()}")

        # 2. Check Gemma pattern (allowing only Google model references)
        if NOVA_PATTERN.search(line):
            lower_line = line.lower()
            if not any(allowed in lower_line for allowed in ALLOWED_NOVA_SUBSTRINGS):
                violations.append(f"{filename}:{lineno} [Personal identifier: Nova] -> {line.strip()}")

    return violations

class PrivacyLeakGuardTests(unittest.TestCase):
    def test_no_personal_identifiers_in_tracked_files(self):
        """Ensure all git-tracked files in the repository contain zero personal identifiers."""
        r = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True)
        tracked_files = [f.strip() for f in r.stdout.splitlines() if f.strip()]

        all_violations = []
        for rel_path in tracked_files:
            # Skip this test file itself so pattern definitions aren't flagged
            if rel_path == 'tests/test_privacy_leak_guard.py':
                continue

            file_path = ROOT / rel_path
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() in BINARY_EXTENSIONS:
                continue

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as exc:
                continue

            violations = scan_text_for_leaks(content, rel_path)
            if violations:
                all_violations.extend(violations)

        self.assertEqual(
            all_violations,
            [],
            "Personal data or identifiers detected in repository:\n" + "\n".join(all_violations)
        )

    def test_scanner_detects_prohibited_terms(self):
        """Verify the leak detection scanner triggers on all prohibited identifiers."""
        self.assertTrue(scan_text_for_leaks("Hello Friend, welcome!"))
        self.assertTrue(scan_text_for_leaks("Author: Friend"))
        self.assertTrue(scan_text_for_leaks("Talking with Sam today"))
        self.assertTrue(scan_text_for_leaks("Connecting to TamanitomoHost over tailscale"))
        self.assertTrue(scan_text_for_leaks("Host: TamanitomoHost"))
        self.assertTrue(scan_text_for_leaks("http://127.0.0.1:38439"))
        self.assertTrue(scan_text_for_leaks("https://her.example.com"))
        self.assertTrue(scan_text_for_leaks("/home/user/projects"))
        self.assertTrue(scan_text_for_leaks("My name is Nova"))

        # Allowed model references should NOT trigger
        self.assertFalse(scan_text_for_leaks("{'provider': 'openrouter', 'model': 'google/gemma-4-26b-a4b-it:free'}"))
        self.assertFalse(scan_text_for_leaks("if 'gemma' in nl: family = 'Gemma'"))

if __name__ == '__main__':
    unittest.main()
