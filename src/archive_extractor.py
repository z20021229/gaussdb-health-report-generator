"""Archive extraction entry points.

The first project phase only prepares the public interface. Real archive
handling will be added in later phases.
"""

from pathlib import Path


def prepare_workdir(workdir: Path) -> Path:
    """Create and return the working directory used by the pipeline."""
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir
