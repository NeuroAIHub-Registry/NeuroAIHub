"""NeuroAIChatAgent: the NeuroAIHub chat agent for Python scripts and notebooks (the same agent as on the website)."""
import base64
import io

from .agent import NeuroAIAgent
from .agent_tools import DatasetTools
from . import data
from .data import load_database


def _in_notebook():
    """True inside Jupyter/Colab (rich display), False in a terminal or script."""
    try:
        from IPython import get_ipython
        shell = get_ipython()
    except Exception:
        return False
    return shell is not None and type(shell).__name__ != "TerminalInteractiveShell"


class NeuroAIChatAgent:
    """Chat with the NeuroAIHub database of neuroradiology datasets.

    agent = NeuroAIChatAgent(api_key="...", base_url="https://openrouter.ai/api/v1",
                             model="cohere/north-mini-code:free")
    result = agent.chat("Which open glioma MRI datasets have segmentation masks?")
    agent.display(result)

    Works with any OpenAI-compatible endpoint whose model supports tool (function) calling; leave base_url empty for
    OpenAI. The conversation is remembered, so follow-up questions ("which of those are open access?") work.
    """

    def __init__(self, api_key, base_url=None, model=None, verbose=False, data_dir=None, refresh_data=False):
        if not api_key or not model:
            raise ValueError("api_key and model are required, e.g. model='gpt-5' or "
                             "model='cohere/north-mini-code:free' with base_url='https://openrouter.ai/api/v1'")
        self.api_key = str(api_key).strip()
        self.base_url = (str(base_url).strip() or None) if base_url else None
        self.model = str(model).strip()
        self.verbose = verbose
        # Latest database from GitHub (cached for a day); data_dir reads a local folder instead.
        self.dataframes, self.combined_df, self.categories = load_database(data_dir, refresh=refresh_data)
        self.data_source = data.last_source
        if verbose:
            print(f"[data] {len(self.combined_df)} datasets from {self.data_source}")
        self.reset()

    def reset(self):
        """Start a new conversation (forgets the history and the previous search results)."""
        self.tools = DatasetTools(self.combined_df, self.categories)
        self.history = []
        self.last_found_datasets = None

    def chat(self, query: str) -> dict:
        """Ask one question. Returns a dict with:
        text (the answer), data (DataFrame of the datasets found, or None), image_b64 (first chart as base64 PNG, or
        None), images (all charts), steps (database lookups made), error (message if the model provider failed),
        status (ok / rate_limited / provider_error / failed / no_answer), model_calls.
        """
        agent = NeuroAIAgent(self.tools, self.api_key, self.model, self.base_url)
        r = agent.ask(query, self.history)
        data = r.tables[-1][1] if r.tables else None
        if data is not None:
            self.last_found_datasets = data
        if not r.error:
            self.history += [{"role": "user", "content": query}, {"role": "assistant", "content": r.text}]
        if self.verbose:
            for name, args in r.steps:
                print(f"[lookup] {name}({args})")
            print(f"[{r.status}] {r.model_calls} model call(s)")
        return {"text": r.text or r.error, "data": data, "image_b64": r.images[0] if r.images else None,
                "images": r.images, "steps": r.steps, "error": r.error, "status": r.status, "model_calls": r.model_calls}

    def display(self, result: dict):
        """Show an answer: text, result table and charts (rich output in Jupyter, plain text in a terminal)."""
        ipy_display = None
        if _in_notebook():
            from IPython.display import Image, Markdown, display as ipy_display
        if ipy_display:
            ipy_display(Markdown(result["text"]))
        else:
            print("\nNeuroAI:\n" + result["text"].strip())
        data = result.get("data")
        if data is not None and not data.empty:
            if ipy_display:
                ipy_display(data)
            else:
                print(f"\n{len(data)} dataset(s):")
                print(data[["category", "dataset_name", "year", "access_type"]].head(20).to_string(index=False, max_colwidth=60))
        for img in result.get("images") or []:
            png = base64.b64decode(img)
            if ipy_display:
                ipy_display(Image(data=png))
            else:
                import matplotlib.pyplot as plt
                plt.figure(figsize=(9, 5))
                plt.imshow(plt.imread(io.BytesIO(png), format="png"))
                plt.axis("off")
                plt.show()
