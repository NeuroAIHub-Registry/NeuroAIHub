"""NeuroAIHub: discover neuroradiology datasets with an AI chat agent (the same agent as on the NeuroAIHub website)."""
from neuroaihub.chat import NeuroAIChatAgent
from neuroaihub.data import load_database

__version__ = "1.1.0"

# Fingerprint of the package source files when they were loaded; the website uses it to notice updated files.
from pathlib import Path as _Path
_SOURCE_STAMP = tuple(sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                             for p in _Path(__file__).resolve().parent.glob("*.py")))
__all__ = ["NeuroAIChatAgent", "load_database", "__version__"]
