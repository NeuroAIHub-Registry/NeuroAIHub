"""NeuroAIHub: discover neuroradiology datasets with an AI chat agent (the same agent as on the NeuroAIHub website)."""
from neuroaihub.chat import NeuroAIChatAgent
from neuroaihub.data import load_database

__version__ = "1.1.0"
__all__ = ["NeuroAIChatAgent", "load_database", "__version__"]
