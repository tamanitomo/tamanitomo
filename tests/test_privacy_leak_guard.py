"""Privacy and secret sanitization regression test.

Guarantees that no private cryptographic keys, live API credentials,
unhashed tokens, or configured confidential developer identifiers leak into
tracked repository files as development continues.
"""
from __future__ import annotations
import json
import os
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

# Standard secret & credential patterns that should never appear in git
STANDARD_FORBIDDEN_PATTERNS = [
    (re.compile(r'-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PGP)?\s*PRIVATE\s+KEY-----'), "Private cryptographic key"),
    (re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b'), "GitHub Personal Access Token"),
    (re.compile(r'\bsk-[a-zA-Z0-9]{20,}\b'), "OpenAI / API Secret Key"),
    (re.compile(r'\bxai-[a-zA-Z0-9]{20,}\b'), "xAI Secret Key"),
    (re.compile(r'https?://[a-zA-Z0-9_-]+:[^@\s/]+@[a-zA-Z0-9.-]+'), "URL with embedded password"),
]

# Local custom patterns file (gitignored, for developer-specific redactions)
CONFIG_PATHS = [
    ROOT / '.leak-patterns.json',
    ROOT / '.leak-patterns',
    pathlib.Path.home() / '.config' / 'tamanitomo' / 'leak-patterns.json',
]


def load_custom_patterns() -> list[tuple[re.Pattern, str, list[str]]]:
    """Load developer-specific leak patterns from local gitignored configuration or env."""
    patterns: list[tuple[re.Pattern, str, list[str]]] = []
    raw_data = None

    # 1. Check environment variable
    env_patterns = os.environ.get('TAMANITOMO_LEAK_PATTERNS')
    if env_patterns:
        try:
            raw_data = json.loads(env_patterns)
        except Exception:
            pass

    # 2. Check local files
    if not raw_data:
        for p in CONFIG_PATHS:
            if p.is_file():
                try:
                    raw_data = json.loads(p.read_text(encoding='utf-8'))
                    break
                except Exception:
                    pass

    if isinstance(raw_data, list):
        for entry in raw_data:
            if isinstance(entry, dict) and 'pattern' in entry:
                try:
                    pat = re.compile(entry['pattern'], re.IGNORECASE)
                    label = entry.get('label', 'Confidential identifier')
                    allowed = entry.get('allowed_substrings', [])
                    patterns.append((pat, label, allowed))
                except Exception:
                    pass
    return patterns


def scan_text_for_leaks(text: str, filename: str = '', custom_patterns: list | None = None) -> list[str]:
    """Scan text content and return any violation strings with line numbers."""
    violations = []
    lines = text.splitlines()
    active_custom = load_custom_patterns() if custom_patterns is None else custom_patterns

    for lineno, line in enumerate(lines, 1):
        # 1. Check standard forbidden patterns
        for pattern, label in STANDARD_FORBIDDEN_PATTERNS:
            if pattern.search(line):
                violations.append(f"{filename}:{lineno} [{label}] -> {line.strip()}")

        # 2. Check custom confidential patterns
        for pattern, label, allowed in active_custom:
            if pattern.search(line):
                lower_line = line.lower()
                if not any(a.lower() in lower_line for a in allowed):
                    violations.append(f"{filename}:{lineno} [{label}] -> {line.strip()}")

    return violations


class PrivacyLeakGuardTests(unittest.TestCase):
    def test_no_personal_identifiers_in_tracked_files(self):
        """Ensure all git-tracked files in the repository contain zero personal or secret identifiers."""
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
            except Exception:
                continue

            violations = scan_text_for_leaks(content, rel_path)
            if violations:
                all_violations.extend(violations)

        self.assertEqual(
            all_violations,
            [],
            "Personal data or credentials detected in repository:\n" + "\n".join(all_violations)
        )

    def test_scanner_detects_prohibited_terms(self):
        """Verify the leak detection scanner triggers on prohibited secrets and custom patterns."""
        # Standard secret detectors
        self.assertTrue(scan_text_for_leaks("-----BEGIN OPENSSH PRIVATE KEY-----"))
        self.assertTrue(scan_text_for_leaks("ghp_1234567890abcdefghijklmnopqrstuvwxyz12"))
        self.assertTrue(scan_text_for_leaks("sk-1234567890abcdef1234567890abcdef123456"))
        self.assertTrue(scan_text_for_leaks("xai-1234567890abcdef1234567890abcdef123456"))
        self.assertTrue(scan_text_for_leaks("https://service-user:supersecretpass123@example.internal/api"))

        # Custom patterns (using synthetic confidential test term)
        synthetic_custom = [
            (re.compile(r'\bclassified_term\b', re.IGNORECASE), "Confidential test identifier", ["allowed_classified_term"])
        ]
        self.assertTrue(scan_text_for_leaks("Found a classified_term in code", custom_patterns=synthetic_custom))
        self.assertFalse(scan_text_for_leaks("Found an allowed_classified_term in code", custom_patterns=synthetic_custom))

        # Benign text should NOT trigger
        self.assertFalse(scan_text_for_leaks("Tamanitomo is a companion application."))
        self.assertFalse(scan_text_for_leaks("{'provider': 'openrouter', 'model': 'google/gemma-4-26b-a4b-it:free'}"))


if __name__ == '__main__':
    unittest.main()
