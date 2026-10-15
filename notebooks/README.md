# Notebooks

Analysis notebooks - exploration, not production code. Last reviewed:
2026-10-15.

| Notebook | Purpose | Feeds |
|----------|---------|-------|
| `01_document_exploration.ipynb` | Chunking strategy comparison on the real corpus | `CHUNK_SIZE` / `CHUNK_OVERLAP` settings |
| `02_evaluation_analysis.ipynb` | Metric distributions, drift charts from eval reports | Golden-set threshold tuning (ADR-0007) |

## Conventions

- Notebooks read from `data/` and write nothing outside `data/processed/`
  and `data/eval/` (both git-ignored for outputs).
- Every notebook starts with the same setup cell (paths, style) - copy
  it rather than reinventing.
- Conclusions belong in the notebook AND in the ADR/doc the decision
  affects - notebooks rot; docs are maintained.

```python
# Standard first cell
import sys, pathlib
ROOT = pathlib.Path.cwd().parent if pathlib.Path.cwd().name == "notebooks" else pathlib.Path.cwd()
sys.path.insert(0, str(ROOT))
```
