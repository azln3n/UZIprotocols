from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_in_os(path: Path) -> None:
    """
    Open file with OS default handler.
    """
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # noqa: S603
        return
    subprocess.Popen(["xdg-open", str(path)])  # noqa: S603

