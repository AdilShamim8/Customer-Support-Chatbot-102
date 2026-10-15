"""
Import isolation contract.

Core modules (parsing, chunking, indexing, retrieval) must import cleanly
even when the optional heavy format backends are absent. This locks in the
lazy-import policy in src/parsing/document_parser.py: a missing
`unstructured`, `pdfplumber`, `bs4` or `python-docx` install must never
break the import chain - it may only disable that format's parser at
runtime (the AI strategy degrades to rule-based parsing).

The check runs in a subprocess with import blockers installed on
sys.meta_path, so it can neither be polluted by, nor pollute, the parent
test process's module cache. It stays honest in CI too, where the
backends ARE installed: the blocker simulates their absence.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Top-level package names of the optional heavy backends.
BLOCKED = ("unstructured", "pdfplumber", "bs4", "docx")

_PROBE = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    class _BlockOptionalBackends:
        \"\"\"Meta-path finder simulating the backends not being installed.\"\"\"

        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in __BLOCKED__:
                raise ImportError(
                    f"simulated absence of optional backend: {fullname}"
                )
            return None

    sys.meta_path.insert(0, _BlockOptionalBackends())

    # The full core import chain that retrieval, indexing and tests rely on.
    import src.parsing.document_parser as dp
    import src.indexing.hybrid_index as hi

    # Module-level symbols survive without the backends.
    assert dp.DocumentType.PDF.value == "pdf"
    assert dp.ParseStrategy.AI_BASED.value == "ai_based"
    assert callable(dp.DocumentParserFactory.parse)
    assert callable(hi.reciprocal_rank_fusion)

    # Parser SELECTION must not touch a backend either - backends are only
    # allowed to load inside parse(), when a real file of that format shows up.
    for name, strategy in [
        ("doc.pdf", dp.ParseStrategy.RULE_BASED),
        ("doc.pdf", dp.ParseStrategy.AI_BASED),
        ("doc.html", dp.ParseStrategy.RULE_BASED),
        ("doc.docx", dp.ParseStrategy.RULE_BASED),
        ("doc.md", dp.ParseStrategy.RULE_BASED),
    ]:
        parser = dp.DocumentParserFactory.get_parser(Path(name), strategy)
        assert parser is not None, (name, strategy)

    print("core imports and parser selection are dependency-light: OK")
    """
)


def test_core_imports_without_optional_format_backends():
    """Importing the core chain must not require any heavy backend."""
    proc = subprocess.run(
        # Fixed probe string written in this file - not untrusted input.
        [sys.executable, "-c", _PROBE.replace("__BLOCKED__", repr(set(BLOCKED)))],  # noqa: S603
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        "core import chain pulled in an optional heavy backend "
        f"(lazy-import policy violated):\n{proc.stderr}"
    )
