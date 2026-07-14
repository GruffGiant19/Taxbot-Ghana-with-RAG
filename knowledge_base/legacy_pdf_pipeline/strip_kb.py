"""
strip_kb.py
-----------
Reads cleaned_kb.md and produces stripped_kb.md with:
  1. The entire "About TaxBot Ghana" section (Section 1) removed.
  2. All section/sub-section headers removed (e.g. "1.", "2.3", "4.2.1 Title").

Run:
    python knowledge_base/strip_kb.py
"""

import re
from pathlib import Path

INPUT_FILE  = Path(__file__).parent / "cleaned_kb.md"
OUTPUT_FILE = Path(__file__).parent / "stripped_kb.md"

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches section headers like:
#   "1.", "2.  Knowledge Base", "3.1  Personal Income Tax", "9.2.1  Whatever"
# Anchored to start of line, number followed by optional sub-numbers and a title.
SECTION_HEADER_RE = re.compile(
    r"^\d+(\.\d+)*\.?\s+\S.*$",
    re.MULTILINE,
)

# The "About TaxBot Ghana" block starts after the document title lines and
# runs from the line beginning "1. About TaxBot Ghana" up to (but not
# including) "2.  Knowledge Base".
# We delete everything from Section 1 up to the start of Section 2.
ABOUT_SECTION_RE = re.compile(
    r"^1\.\s+About TaxBot Ghana.*?(?=^\d+\.\s)",
    re.DOTALL | re.MULTILINE,
)


def strip_document(text: str) -> str:
    # -----------------------------------------------------------------------
    # Step 1 — Remove the entire "About TaxBot Ghana" section (Section 1)
    # -----------------------------------------------------------------------
    text = ABOUT_SECTION_RE.sub("", text)

    # -----------------------------------------------------------------------
    # Step 2 — Remove section / sub-section header lines
    # -----------------------------------------------------------------------
    text = SECTION_HEADER_RE.sub("", text)

    # -----------------------------------------------------------------------
    # Step 3 — Collapse runs of 3+ blank lines into at most 2 blank lines
    #           (keeps the document readable without giant gaps)
    # -----------------------------------------------------------------------
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"[ERROR] Input file not found: {INPUT_FILE}")
        return

    raw = INPUT_FILE.read_text(encoding="utf-8")
    cleaned = strip_document(raw)
    OUTPUT_FILE.write_text(cleaned, encoding="utf-8")

    original_lines = raw.count("\n") + 1
    new_lines      = cleaned.count("\n") + 1
    removed        = original_lines - new_lines

    print(f"Done!")
    print(f"  Input : {INPUT_FILE.name}  ({original_lines} lines)")
    print(f"  Output: {OUTPUT_FILE.name} ({new_lines} lines)")
    print(f"  Removed ~{removed} lines")


if __name__ == "__main__":
    main()
