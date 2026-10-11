"""Build experiments/diagrams/_preview_run.js from Mermaid files.

Usage: python experiments/mermaid_preview.py a.mmd b.mmd, then run the
generated script with Playwright's ``browser_run_code``; the screenshots land
in experiments/diagrams/preview-N.png.
"""

import json
import pathlib
import sys

here = pathlib.Path(__file__).parent
source = (here / "mermaid_preview.js").read_text()
diagrams = json.dumps(
    [pathlib.Path(name).read_text() for name in sys.argv[1:]], ensure_ascii=False
)
out = here / "diagrams" / "_preview_run.js"
out.parent.mkdir(exist_ok=True)
out.write_text(source.replace("globalThis.DIAGRAMS || []", diagrams))
print(out)
