"""NeuroAI chat agent: a small tool-calling loop on any OpenAI-compatible endpoint (OpenAI, OpenRouter, ...).

One user question normally costs two model calls: one that picks a tool with structured filters, and one that writes
the answer from the tool result. All facts come from agent_tools.DatasetTools.
"""
import json
import re
import time
import uuid
from dataclasses import dataclass, field

from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from .agent_tools import DatasetTools

MAX_STEPS = 5          # tool rounds per question
HISTORY_TURNS = 6      # previous user/assistant exchanges sent to the model
RETRIES = 2            # extra attempts on rate limits / transient errors

SYSTEM_PROMPT = """You are NeuroAI, the assistant of NeuroAIHub, a curated database of {n} public neuroradiology imaging datasets.
Categories and their most common diseases:
{categories}

RULES
1. Every dataset name, number, link and fact you state must come from a tool result in this conversation. Never invent datasets, counts, URLs or metadata, and never rely on your own memory of datasets. If the tools do not return it, say the database does not contain it. Do not name or recommend datasets outside the database, even well-known ones.
2. Use tools for every question about the data. Choose the most specific tool:
   - find / list / filter / "which datasets" / recommendations -> search_datasets
   - one named dataset's details (DOI, protocol, resolution, age range, ...) -> get_dataset_details
   - counts, "how many", distributions, rankings, comparisons, plots/charts -> count_datasets (set chart when the user wants a plot; use split_by for several series, e.g. MRI vs CT per year)
   - scatter plots, histograms or box plots of year / number of subjects / number of scans -> numeric_chart
   - overview / summary of a category or of the whole database -> summarize_category
   - anything the tools above cannot express -> run_python (last resort)
3. Map the user's words onto the database vocabulary:
   - Disease terms in the database: {diseases}.
     For broad concepts pass several terms or use the category, e.g. "brain tumors" -> category Neoplasm; "dementia" -> Alzheimer's Disease, Dementia, Frontotemporal Dementia, Lewy Body Disease; "healthy volunteers / normative" -> Healthy.
   - Modalities: {modalities}. fMRI, DTI, DWI, MRA, SWI, ASL are MRI; CTA is CT.
   - Segmentation masks, healthy controls, clinical data, histopathology, lab data and staging are yes/no filters; access is Open or Restricted.
4. If a search returns 0 matches, do not guess: tell the user, and use the "relaxations" field to suggest which filter to drop (you may run one relaxed search). Do not suggest alternative datasets or topics unless a tool returned them.
   Never fabricate, estimate or simulate data for a chart or table; if the tools cannot produce it, say so.
5. Follow-up questions about "these/those datasets" -> search_datasets with within_previous_results=true plus the new filter.
6. Apply only the filters the user asked for; do not add extra ones (such as access or year) on your own.
7. For recommendations, search with the user's requirements, then recommend the 3-5 best matches and say why (size, masks, access, modality, recency). Fetch details only if needed.

ANSWER STYLE
- Concise Markdown in the user's language. Start with the direct answer (e.g. the number of matches).
- List at most 10 datasets as bullets: **Name** (year) — modality; subjects; access; [link](url). The full result table and any chart are shown to the user automatically below your answer, so say so instead of listing everything.
- Do not show raw JSON or tool names."""


@dataclass
class AgentResult:
    text: str
    tables: list = field(default_factory=list)   # [(title, DataFrame)]
    images: list = field(default_factory=list)   # [base64 PNG]
    steps: list = field(default_factory=list)    # [(tool name, arguments)]
    model_calls: int = 0
    error: str = ""
    status: str = "ok"     # ok | rate_limited | provider_error | failed | no_answer


def _clean_text(text):
    """Strip reasoning blocks some open models put in the content."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return re.sub(r"^\s*</?think>\s*", "", text).strip()


_TEXT_TOOL_CALL = re.compile(r"\{[^{}]*\"name\"\s*:\s*\"(\w+)\"[^{}]*\"(?:arguments|parameters)\"\s*:\s*(\{.*?\})\s*\}", re.S)


_XML_INVOKE = re.compile(r'<invoke\s+name="(\w+)"\s*>(.*?)</invoke>', re.S)
_XML_PARAM = re.compile(r'<parameter\s+name="(\w+)"[^>]*>(.*?)</parameter>', re.S)


def _tool_calls_from_text(text, tool_names):
    """Some open models write the tool call as text (JSON, or <invoke>/<parameter> XML) instead of using the
    tool-call field."""
    found = [(m.group(1), m.group(2)) for m in _TEXT_TOOL_CALL.finditer(text or "")]
    for m in _XML_INVOKE.finditer(text or ""):
        params = {}
        for p in _XML_PARAM.finditer(m.group(2)):
            raw = p.group(2).strip()
            try:
                params[p.group(1)] = json.loads(raw)
            except ValueError:
                params[p.group(1)] = raw
        found.append((m.group(1), json.dumps(params)))
    return [{"id": "call_" + uuid.uuid4().hex[:12], "type": "function", "function": {"name": n, "arguments": a}}
            for n, a in found if n in tool_names]


class NeuroAIAgent:
    def __init__(self, tools: DatasetTools, api_key: str, model: str, base_url: str = None, timeout: float = 120):
        self.tools = tools
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout, max_retries=0)
        self.schemas = tools.schemas()
        self.tool_names = {s["function"]["name"] for s in self.schemas}
        self.system = SYSTEM_PROMPT.format(
            n=len(tools.df), categories=self._category_lines(), diseases="; ".join(tools.diseases),
            modalities=", ".join(tools.modalities))

    def _category_lines(self):
        df = self.tools.df
        lines = []
        for c in self.tools.categories:
            sub = df[df["category"] == c]
            top = sub["_dis"].explode().value_counts()
            top = [t for t in top.index if t != "Healthy"][:6]
            lines.append(f"- {c} ({len(sub)} datasets): {', '.join(top)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ model call with retries
    def _complete(self, messages, use_tools=True):
        kwargs = dict(model=self.model, messages=messages, temperature=0)
        if use_tools:
            kwargs.update(tools=self.schemas, tool_choice="auto")
        last = None
        for attempt in range(RETRIES + 1):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                if not resp.choices:
                    raise RuntimeError(getattr(resp, "error", None) or "empty response from provider")
                return resp.choices[0].message
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                last = e
            except APIStatusError as e:
                if e.status_code < 500:
                    raise
                last = e
            except RuntimeError as e:
                last = e
            if attempt < RETRIES:
                time.sleep(4 * (attempt + 1))
        raise last

    # ------------------------------------------------------------------ one user turn
    def ask(self, question: str, history=None) -> AgentResult:
        self.tools.tables, self.tools.images = [], []
        result = AgentResult(text="")
        messages = [{"role": "system", "content": self.system}]
        for turn in (history or [])[-2 * HISTORY_TURNS:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": question})

        nudged = False
        try:
            for step in range(MAX_STEPS + 1):
                final_round = step == MAX_STEPS
                msg = self._complete(messages, use_tools=not final_round)
                result.model_calls += 1
                content = _clean_text(msg.content)
                calls = [{"id": c.id or "call_" + uuid.uuid4().hex[:12], "type": "function",
                          "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                         for c in (msg.tool_calls or [])]
                if not calls and not final_round:
                    calls = _tool_calls_from_text(content, self.tool_names)
                    if calls:
                        content = ""
                if not calls and step == 0 and not nudged and len(question.split()) >= 3:
                    # The model answered from memory; ask it once to check the database first.
                    nudged = True
                    messages.append({"role": "assistant", "content": content or ""})
                    messages.append({"role": "user", "content": "Check this against the database with the tools before answering. "
                                                                "Do not answer from memory or from earlier messages alone."})
                    continue
                if not calls:
                    if content:
                        result.text = content
                        break
                    # Empty answer: ask once more without tools.
                    messages.append({"role": "user", "content": "Please answer the question now based on the tool results above."})
                    continue
                messages.append({"role": "assistant", "content": content or None, "tool_calls": calls})
                for c in calls:
                    name, args = c["function"]["name"], c["function"]["arguments"]
                    out = self.tools.call(name, args)
                    try:
                        parsed = json.loads(args) if isinstance(args, str) else args
                    except Exception:
                        parsed = args
                    result.steps.append((name, parsed))
                    messages.append({"role": "tool", "tool_call_id": c["id"], "name": name,
                                     "content": json.dumps(out, ensure_ascii=False, default=str)})
            if not result.text:
                result.status = "no_answer"
                result.text = "I couldn't finish this answer. Please rephrase the question or try another model."
        except RateLimitError:
            result.status = "rate_limited"
            result.error = ("The model provider is rate-limiting requests right now (common with free models). "
                            "Wait a minute and try again, or switch to another model.")
        except APIStatusError as e:
            result.status = "provider_error"
            detail = ""
            try:
                detail = e.response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            result.error = f"The model provider returned an error ({e.status_code}): {detail or e.message}"
        except Exception as e:
            result.status = "failed"
            result.error = f"The model provider failed to answer ({e}). Please try again or switch to another model."
        result.tables, result.images = list(self.tools.tables), list(self.tools.images)
        return result
