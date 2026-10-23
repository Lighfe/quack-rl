"""No test names a ruleset before v2.

Every `*.py` file under tests/ (outside tests/fixtures/) is scanned for the quoted version
strings of the retired rulesets. A line that ends with the comment `# old-version-ok` is skipped.
The pattern and the examples are built from parts, so this file does not match its own pattern.
"""

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SKIP_MARK = "# old-version-ok"
V = "v" + "1"  # the stem of the retired versions
OLD = re.compile(r"""(["'])""" + V + r"""(\.(?:1|8|9|10|11))?\1""")


def old_version_lines(text: str) -> list[tuple[int, str]]:
    """The lines with a quoted old version string, except those that end with the skip comment."""
    return [
        (n, line)
        for n, line in enumerate(text.splitlines(), start=1)
        if OLD.search(line) and not line.rstrip().endswith(SKIP_MARK)
    ]


def test_check_passes_rules_v2():
    assert old_version_lines('load_ruleset(rules="v2")') == []


def test_check_passes_a_line_with_the_skip_comment():
    line = 'assert x == "' + V + '.11"  ' + SKIP_MARK
    assert old_version_lines(line) == []


def test_check_denies_an_old_rules_argument():
    assert old_version_lines('load_ruleset(rules="' + V + '.11")')


def test_check_denies_a_list_of_versions():
    assert old_version_lines('VERSIONS = ["' + V + '", "v2"]')
    assert old_version_lines("VERSIONS = ['" + V + ".8']")


def test_check_ignores_other_suffixes():
    # a literal with another suffix is not an old version string
    assert old_version_lines('name = "' + V + '_golden"') == []
    assert old_version_lines('load_ruleset("' + V + '.12")') == []


def test_no_old_versions_in_tests():
    found = []
    for path in sorted(TESTS.rglob("*.py")):
        relative = path.relative_to(TESTS)
        if relative.parts[0] == "fixtures" or "__pycache__" in relative.parts:
            continue
        for n, line in old_version_lines(path.read_text(encoding="utf-8")):
            found.append(f"{relative}:{n}: {line.strip()}")
    assert not found, "old version strings in tests:\n" + "\n".join(found)
