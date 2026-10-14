"""Deterministic tools for the NeuroAI chat agent.

The language model only chooses a tool and fills in structured arguments; every number, dataset name and link in an
answer comes from these functions, computed directly from the database. Results are kept small for the model, while
the full tables and charts are handed to the UI.
"""
import ast
import base64
import collections
import contextlib
import difflib
import io
import json
import math
import re
import statistics

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .data import COLUMNS, split_terms, yes_no

YES_NO_FIELDS = ["segmentation_mask", "healthy_control", "clinical_data", "histopathology", "lab_data", "staging_information"]
COUNT_FIELDS = ["category", "year", "modality", "disease", "country", "format", "access_type"] + YES_NO_FIELDS
PALETTE = ["#1AA3D9", "#7AD9FF", "#123B4A", "#4FC3F7", "#0D8AB8", "#A8E4FF", "#2B7A9E", "#5BC0DE", "#84A9B8", "#3E6A7A"]
SERIES_COLORS = ["#1AA3D9", "#123B4A", "#E8833A", "#7AD9FF", "#2E9E6B", "#B8860B", "#8E6CC0", "#84A9B8"]
MAX_ROWS_FOR_MODEL = 25
NUMERIC_FIELDS = ["year", "subject_no", "slice_scan_no"]


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s).replace("’", "'").replace("‘", "'").lower()).strip()


def _short(s, n=110) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _first_url(row) -> str:
    for field in ("url", "doi"):
        m = re.search(r"https?://[^\s,;<>()]+", str(row[field]))
        if m:
            return m.group(0).rstrip(".)]")
    m = re.search(r"\b10\.\d{4,9}/[^\s,;<>()]+", str(row["doi"]))
    return "https://doi.org/" + m.group(0).rstrip(".)]") if m else "Not specified"


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


class DatasetTools:
    def __init__(self, combined_df: pd.DataFrame, categories: list):
        df = combined_df.reset_index(drop=True).copy()
        self.categories = list(categories)
        # Parsed, list-valued columns used for exact term matching.
        df["_mods"] = df["modality"].map(split_terms)
        df["_dis"] = df["disease"].map(split_terms)
        df["_fmt"] = df["format"].map(split_terms)
        df["_ctry"] = df["country"].map(split_terms)
        df["_access"] = df["access_type"].map(lambda v: (split_terms(v) or ["Not specified"])[0])
        for f in YES_NO_FIELDS:
            df["_" + f] = df[f].map(yes_no)
        df["_year"] = df["year_clean"]
        df["_subjects"] = df["subject_no_clean"]
        df["_link"] = df.apply(_first_url, axis=1)
        df["_text"] = df.apply(lambda r: _norm(" ".join(str(r[c]) for c in COLUMNS + ["category"])), axis=1)
        self.df = df

        def vocab(col):
            return sorted({t for terms in df[col] for t in terms}, key=str.lower)
        self.diseases, self.modalities = vocab("_dis"), vocab("_mods")
        self.formats, self.countries = vocab("_fmt"), vocab("_ctry")
        self.previous_ids = []      # row ids of the last search, for follow-up questions
        self.tables = []            # (title, DataFrame) produced during one turn, shown in the UI
        self.images = []            # base64 PNG charts produced during one turn

    # ------------------------------------------------------------------ schemas
    def _filter_properties(self):
        yn = {"type": "string", "enum": ["yes", "no"]}
        return {
            "category": {"type": "string", "enum": self.categories, "description": "Database category (sheet)."},
            "diseases": {"type": "array", "items": {"type": "string"},
                         "description": "Disease terms; a dataset matches if it has ANY of them. Use the database's disease vocabulary."},
            "modalities": {"type": "array", "items": {"type": "string", "enum": self.modalities},
                           "description": "Imaging modalities."},
            "modality_match": {"type": "string", "enum": ["any", "all"],
                               "description": "'all' = dataset must include every listed modality (e.g. both MRI and PET). Default 'any'."},
            "access": {"type": "string", "enum": ["Open", "Restricted"]},
            "segmentation_mask": dict(yn, description="Has segmentation masks/labels."),
            "healthy_control": dict(yn, description="Includes healthy controls."),
            "clinical_data": yn, "histopathology": yn, "lab_data": yn, "staging_information": yn,
            "year_from": {"type": "integer"}, "year_to": {"type": "integer"},
            "min_subjects": {"type": "integer"}, "max_subjects": {"type": "integer"},
            "countries": {"type": "array", "items": {"type": "string"}},
            "formats": {"type": "array", "items": {"type": "string"}, "description": "Image file formats, e.g. NIFTI, DICOM."},
            "keywords": {"type": "string",
                         "description": "Free-text words that must ALL appear somewhere in the dataset's metadata "
                                        "(e.g. 'longitudinal', 'DTI', '7T', 'pediatric', a dataset or institution name)."},
            "within_previous_results": {"type": "boolean",
                                        "description": "Restrict to the datasets found by the previous search (follow-up questions)."},
        }

    def schemas(self):
        filters = self._filter_properties()
        return [
            {"type": "function", "function": {
                "name": "search_datasets",
                "description": "Find datasets matching filters. Returns the total number of matches and the top matches "
                               "(name, year, modality, disease, subjects, access, masks, link). The full result table is shown to the user automatically.",
                "parameters": {"type": "object", "properties": {
                    **filters,
                    "sort_by": {"type": "string", "enum": ["newest", "oldest", "most_subjects", "name"]},
                    "limit": {"type": "integer", "description": "How many matches to return to you (default 15, max 25)."},
                }},
            }},
            {"type": "function", "function": {
                "name": "get_dataset_details",
                "description": "Full metadata (all 22 fields: DOI, URL, institution, resolution, protocol, preprocessing, age range, "
                               "clinical/histopathology/lab data, ...) for specific datasets by name.",
                "parameters": {"type": "object", "properties": {
                    "names": {"type": "array", "items": {"type": "string"}, "description": "Dataset names (up to 5)."}},
                    "required": ["names"]},
            }},
            {"type": "function", "function": {
                "name": "count_datasets",
                "description": "Count datasets grouped by a field (optionally after filtering) and optionally draw a chart that is shown to the user. "
                               "Use for 'how many', 'most common', 'distribution', 'per year', 'compare categories', summaries and plots. "
                               "Use split_by for several series in one chart, e.g. 'MRI vs CT per year' = group_by year, split_by modality, "
                               "modalities [MRI, CT], chart line.",
                "parameters": {"type": "object", "properties": {
                    "group_by": {"type": "string", "enum": COUNT_FIELDS},
                    "split_by": {"type": "string", "enum": COUNT_FIELDS,
                                 "description": "Optional second field: one series per value (lines or grouped bars). "
                                                "Only the values selected by the matching filter are kept (e.g. the listed modalities)."},
                    **filters,
                    "top_n": {"type": "integer", "description": "Keep the N largest groups (default 15)."},
                    "chart": {"type": "string", "enum": ["none", "bar", "pie", "line"],
                              "description": "Draw a chart for the user. 'line' only makes sense for group_by=year."},
                    "title": {"type": "string"},
                }, "required": ["group_by"]},
            }},
            {"type": "function", "function": {
                "name": "numeric_chart",
                "description": "Charts of numeric fields (publication year, number of subjects, number of scans/slices) drawn from the "
                               "real data and shown to the user: scatter (x vs y), histogram (distribution of x) or box plot "
                               "(x per group). E.g. 'year vs subjects scatter', 'distribution of dataset sizes', 'subjects per category'.",
                "parameters": {"type": "object", "properties": {
                    "chart": {"type": "string", "enum": ["scatter", "histogram", "box"]},
                    "x": {"type": "string", "enum": NUMERIC_FIELDS, "description": "Numeric field (x axis, or the measured field for histogram/box)."},
                    "y": {"type": "string", "enum": NUMERIC_FIELDS, "description": "Second numeric field (scatter only)."},
                    "group_by": {"type": "string", "enum": ["category", "access_type", "modality"] + YES_NO_FIELDS,
                                 "description": "Colour points (scatter) or one box per value (box)."},
                    "log_scale": {"type": "boolean", "description": "Log scale for subject/scan counts (default true)."},
                    **filters,
                    "title": {"type": "string"},
                }, "required": ["chart", "x"]},
            }},
            {"type": "function", "function": {
                "name": "summarize_category",
                "description": "Statistics for one category or the whole database: dataset count, year range, top diseases and "
                               "modalities, access, masks, healthy controls, subject numbers, newest datasets.",
                "parameters": {"type": "object", "properties": {
                    "category": {"type": "string", "enum": self.categories + ["All"]}}, "required": ["category"]},
            }},
            {"type": "function", "function": {
                "name": "run_python",
                "description": "LAST RESORT for analyses the other tools cannot do. Runs sandboxed pandas/matplotlib code that must compute "
                               "everything from df (never type in or simulate numbers). "
                               "Available: df (one row per dataset; columns " + ", ".join(COLUMNS + ["category"]) + "). "
                               "Columns hold clean values: year and subject_no are numbers (NaN if unknown); access_type is "
                               "'Open' or 'Restricted'; segmentation_mask, healthy_control, clinical_data, histopathology, lab_data, "
                               "staging_information are 'Yes'/'No'/'Not specified'; modality, disease, country, format are "
                               "comma-separated terms, also as lists in _mods, _dis, _ctry, _fmt (use .explode()). Original text "
                               "with details is in <column>_details. Also pd, np, plt, sns. Only pandas/numpy/matplotlib/seaborn/math/collections/statistics can be imported; no files or network. "
                               "Put the answer in a variable named result or as the last expression; any matplotlib figure is shown to the user.",
                "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            }},
        ]

    # ------------------------------------------------------------------ filtering
    def _match_terms(self, wanted, vocab, broad=False):
        """Map user terms onto vocabulary terms: exact, then substring either way (case/apostrophe-insensitive).
        broad=True also adds the substring matches when there is an exact one ("stroke" -> "Ischemic Stroke" too)."""
        hits, unmatched = set(), []
        for w in wanted or []:
            nw = _norm(w)
            if not nw:
                continue
            exact = [v for v in vocab if _norm(v) == nw]
            sub = [v for v in vocab if nw in _norm(v) or (len(_norm(v)) > 3 and _norm(v) in nw)]
            near = (exact + sub) if broad else (exact or sub)
            if near:
                hits.update(near)
            else:
                unmatched.append(w)
        return hits, unmatched

    def _apply(self, args, skip=None):
        df, notes = self.df, []
        a = {k: v for k, v in args.items() if v not in (None, "", [], "any") and k != skip}
        if a.get("within_previous_results") and self.previous_ids:
            df = df.loc[[i for i in self.previous_ids if i in df.index]]
        if "category" in a and a["category"] != "All":
            df = df[df["category"].str.lower() == str(a["category"]).lower()]
        if a.get("diseases"):
            hits, unmatched = self._match_terms(a["diseases"], self.diseases, broad=True)
            mask = df["_dis"].map(lambda ts: any(t in hits for t in ts))
            for u in unmatched:  # fall back to free text for terms outside the vocabulary
                mask |= df["_text"].str.contains(re.escape(_norm(u)), regex=True)
            df = df[mask]
            if unmatched:
                notes.append(f"Not in the disease vocabulary, matched as free text: {', '.join(unmatched)}")
            if hits:
                notes.append("Disease terms used: " + ", ".join(sorted(hits)))
        if a.get("modalities"):
            hits, _ = self._match_terms(a["modalities"], self.modalities)
            want = hits or set(a["modalities"])
            if args.get("modality_match") == "all":
                df = df[df["_mods"].map(lambda ts: want.issubset(ts))]
            else:
                df = df[df["_mods"].map(lambda ts: any(t in want for t in ts))]
        if a.get("access"):
            df = df[df["_access"].str.lower() == str(a["access"]).lower()]
        for f in YES_NO_FIELDS:
            if a.get(f) in ("yes", "no"):
                df = df[df["_" + f] == a[f]]
        if a.get("year_from"):
            df = df[df["_year"] >= int(a["year_from"])]
        if a.get("year_to"):
            df = df[df["_year"] <= int(a["year_to"])]
        if a.get("min_subjects"):
            df = df[df["_subjects"] >= float(a["min_subjects"])]
        if a.get("max_subjects"):
            df = df[df["_subjects"] <= float(a["max_subjects"])]
        if a.get("countries"):
            hits, _ = self._match_terms(a["countries"], self.countries)
            df = df[df["_ctry"].map(lambda ts: any(t in hits for t in ts))]
        if a.get("formats"):
            hits, _ = self._match_terms(a["formats"], self.formats)
            df = df[df["_fmt"].map(lambda ts: any(t in hits for t in ts))]
        if a.get("keywords"):
            for word in _norm(a["keywords"]).split():
                df = df[df["_text"].str.contains(re.escape(word), regex=True)]
        return df, notes

    def _active_filters(self, args):
        keys = set(self._filter_properties()) - {"modality_match", "within_previous_results"}
        return {k: v for k, v in args.items() if k in keys and v not in (None, "", [])}

    def _relaxations(self, args):
        """For an empty result: how many datasets each single filter removal would give back."""
        out = {}
        for k in self._active_filters(args):
            n = len(self._apply(args, skip=k)[0])
            if n:
                out[f"without {k}"] = n
        return out

    def _ui_table(self, df):
        return df[["category"] + COLUMNS].reset_index(drop=True)

    # ------------------------------------------------------------------ tools
    def search_datasets(self, **args):
        df, notes = self._apply(args)
        sort = args.get("sort_by") or "newest"
        if sort == "oldest":
            df = df.sort_values(["_year", "dataset_name"], na_position="last")
        elif sort == "most_subjects":
            df = df.sort_values("_subjects", ascending=False, na_position="last")
        elif sort == "name":
            df = df.sort_values("dataset_name", key=lambda s: s.str.lower())
        else:
            df = df.sort_values(["_year", "dataset_name"], ascending=[False, True], na_position="last")
        self.previous_ids = list(df.index)
        limit = max(1, min(int(args.get("limit") or 15), MAX_ROWS_FOR_MODEL))
        out = {"total_matches": len(df), "filters": self._active_filters(args)}
        if notes:
            out["notes"] = notes
        if len(df):
            self.tables.append((f"{len(df)} matching dataset{'s' if len(df) != 1 else ''}", self._ui_table(df)))
            out["showing"] = min(limit, len(df))
            out["datasets"] = [{
                "name": r["dataset_name"], "category": r["category"],
                "year": int(r["_year"]) if pd.notna(r["_year"]) else "Not specified",
                "modality": _short(r["modality"], 90), "disease": _short(r["disease"], 90),
                "subjects": _short(r["subject_no"], 60), "access": r["_access"],
                "segmentation_mask": r["_segmentation_mask"], "link": r["_link"],
            } for _, r in df.head(limit).iterrows()]
        else:
            out["relaxations"] = self._relaxations(args)
        return out

    def get_dataset_details(self, names=None, **_):
        found, missing = [], []
        lower = self.df["dataset_name"].map(_norm)
        for name in (names or [])[:5]:
            n = _norm(name)
            idx = list(self.df.index[lower == n]) or list(self.df.index[lower.str.contains(re.escape(n), regex=True)])
            if not idx:
                close = difflib.get_close_matches(n, lower.tolist(), n=2, cutoff=0.55)
                idx = [lower[lower == c].index[0] for c in close]
            if idx:
                found.extend(i for i in idx[:3] if i not in found)
            else:
                missing.append(name)
        rows = self.df.loc[found]
        if len(rows):
            self.tables.append(("Dataset details", self._ui_table(rows)))
        out = {"datasets": [dict({"category": r["category"]}, **{c: r[c] for c in COLUMNS}) for _, r in rows.iterrows()]}
        if missing:
            out["not_found"] = missing
        return out

    def _values(self, df, field):
        """One list of values per dataset for a countable field."""
        if field == "year":
            return df["_year"].map(lambda y: [int(y)] if pd.notna(y) else [])
        if field in ("modality", "disease", "country", "format"):
            return df[{"modality": "_mods", "disease": "_dis", "country": "_ctry", "format": "_fmt"}[field]]
        if field == "access_type":
            return df["_access"].map(lambda v: [v])
        if field in YES_NO_FIELDS:
            return df["_" + field].map(lambda v: [{"yes": "Yes", "no": "No", "ns": "Not specified"}[v]])
        return df[field].map(lambda v: [v])

    def _split_counts(self, df, group_by, split_by, args, top_n):
        pairs = [(g, v) for gs, vs in zip(self._values(df, group_by), self._values(df, split_by)) for g in gs for v in vs]
        table = pd.crosstab(pd.Series([p[0] for p in pairs], name=group_by), pd.Series([p[1] for p in pairs], name=split_by)) \
            if pairs else pd.DataFrame()
        keep = {"modality": ("modalities", self.modalities), "disease": ("diseases", self.diseases),
                "country": ("countries", self.countries), "format": ("formats", self.formats)}.get(split_by)
        if keep and args.get(keep[0]):
            hits, _ = self._match_terms(args[keep[0]], keep[1], broad=split_by == "disease")
            table = table[[c for c in table.columns if c in hits]]
        if split_by == "access_type" and args.get("access"):
            table = table[[c for c in table.columns if c == args["access"]]]
        table = table[table.sum().sort_values(ascending=False).index[:8]] if len(table.columns) else table
        if group_by == "year":
            table = table.sort_index()
            if len(table):
                table = table.reindex(range(int(table.index.min()), int(table.index.max()) + 1), fill_value=0)
        else:
            table = table.loc[table.sum(axis=1).sort_values(ascending=False).index[:top_n]]
        return table

    def _group(self, df, field):
        if field == "year":
            s = df["_year"].dropna().astype(int)
        elif field in ("modality", "disease", "country", "format"):
            col = {"modality": "_mods", "disease": "_dis", "country": "_ctry", "format": "_fmt"}[field]
            s = df[col].explode().dropna()
        elif field == "access_type":
            s = df["_access"]
        elif field in YES_NO_FIELDS:
            s = df["_" + field].map({"yes": "Yes", "no": "No", "ns": "Not specified"})
        else:
            s = df[field]
        return s.value_counts()

    def count_datasets(self, group_by="category", top_n=15, chart="none", title=None, split_by=None, **args):
        df, notes = self._apply(args)
        top_n = max(1, min(int(top_n or 15), 40))
        if split_by and split_by != group_by:
            table = self._split_counts(df, group_by, split_by, args, top_n)
            out = {"datasets_counted": len(df), "group_by": group_by, "split_by": split_by, "filters": self._active_filters(args),
                   "counts": {str(g): {str(c): int(n) for c, n in row.items()} for g, row in table.iterrows()},
                   "series_totals": {str(c): int(n) for c, n in table.sum().items()}}
            if notes:
                out["notes"] = notes
            if chart and chart != "none" and table.size:
                self.images.append(self._multi_chart(table, "line" if chart == "line" else "bar",
                                                     title or f"Datasets by {group_by.replace('_', ' ')} and {split_by.replace('_', ' ')}"))
                out["chart"] = "shown to the user"
            return out
        counts = self._group(df, group_by)
        healthy = 0
        if group_by == "disease" and not args.get("diseases") and "Healthy" in counts.index:
            healthy = int(counts.pop("Healthy"))  # healthy cohorts are not a disease; reported separately
        if group_by == "year":
            counts = counts.sort_index()
        others = 0
        if group_by != "year" and len(counts) > top_n:
            others = int(counts.iloc[top_n:].sum())
            counts = counts.iloc[:top_n]
        out = {"datasets_counted": len(df), "group_by": group_by, "filters": self._active_filters(args),
               "counts": {str(k): int(v) for k, v in counts.items()}}
        if others:
            out["other_values_total"] = others
        if healthy:
            out["healthy_cohorts_excluded_not_a_disease"] = healthy
        if group_by in ("modality", "disease", "country", "format"):
            out["note"] = "A dataset can have several values, so counts can add up to more than datasets_counted."
        if notes:
            out["notes"] = notes
        if chart and chart != "none" and len(counts):
            if not title:
                scope = [args[k] for k in ("category",) if args.get(k)] + list(args.get("diseases") or []) + list(args.get("modalities") or [])
                title = f"Datasets by {group_by.replace('_', ' ')}" + (f" — {', '.join(map(str, scope))}" if scope else "")
            self.images.append(self._chart(counts, chart, title))
            out["chart"] = "shown to the user"
        return out

    def _multi_chart(self, table, kind, title):
        fig, ax = plt.subplots(figsize=(9.5, 4.4))
        colors = (SERIES_COLORS * 2)[: len(table.columns)]
        if kind == "line":
            for col, color in zip(table.columns, colors):
                ax.plot([str(i) for i in table.index], table[col].values, marker="o", linewidth=2.2, label=str(col), color=color)
        else:
            table.plot(kind="bar", ax=ax, color=colors, width=.8)
        ax.tick_params(axis="x", rotation=45)
        ax.set_xlabel("")
        ax.legend(frameon=False)
        ax.set_title(title, color="#123B4A", fontsize=12, fontweight="bold", loc="left")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        return _fig_to_b64(fig)

    def _chart(self, counts, kind, title):
        labels = [str(k) for k in counts.index]
        values = counts.values
        if kind == "line" or (kind == "bar" and counts.index.dtype.kind in "iu"):
            fig, ax = plt.subplots(figsize=(9, 4.2))
            if kind == "line":
                ax.plot(labels, values, color=PALETTE[0], marker="o", linewidth=2.4)
                ax.fill_between(range(len(values)), values, color=PALETTE[1], alpha=.25)
            else:
                ax.bar(labels, values, color=PALETTE[0])
            ax.tick_params(axis="x", rotation=45)
        elif kind == "pie":
            fig, ax = plt.subplots(figsize=(7, 5.5))
            labels = [f"{l} ({v})" for l, v in zip(labels, values)]
            ax.pie(values, labels=labels, autopct=lambda p: f"{p:.0f}%" if p >= 4 else "", startangle=90,
                   colors=(PALETTE * 5)[: len(values)], wedgeprops={"edgecolor": "white"}, textprops={"fontsize": 9})
            ax.axis("equal")
        else:
            fig, ax = plt.subplots(figsize=(9, max(2.6, .42 * len(values) + 1)))
            ax.barh(labels[::-1], values[::-1], color=PALETTE[0])
            for i, v in enumerate(values[::-1]):
                ax.text(v, i, f" {v}", va="center", fontsize=9, color="#123B4A")
        ax.set_title(title, color="#123B4A", fontsize=12, fontweight="bold", loc="left")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        return _fig_to_b64(fig)

    def numeric_chart(self, chart="scatter", x="year", y=None, group_by=None, log_scale=None, title=None, **args):
        df, notes = self._apply(args)
        col = {"year": "_year", "subject_no": "_subjects", "slice_scan_no": "slice_scan_no_clean"}
        label = {"year": "Publication year", "subject_no": "Number of subjects", "slice_scan_no": "Number of scans/slices"}
        if chart == "scatter" and not y:
            y = "subject_no" if x == "year" else "year"
        fields = [x] + ([y] if chart == "scatter" else [])
        data = df.dropna(subset=[col[f] for f in fields])
        out = {"datasets_matching_filters": len(df), "datasets_plotted": len(data), "filters": self._active_filters(args),
               "left_out_because_value_unknown": len(df) - len(data)}
        if notes:
            out["notes"] = notes
        if not len(data):
            return dict(out, error="No datasets with known values to plot.")
        log = (log_scale if log_scale is not None else True)
        groups = None
        if group_by:
            g = self._values(data, group_by).map(lambda v: v[0] if v else "Not specified")
            groups = list(g.value_counts().index[:8])
        fig, ax = plt.subplots(figsize=(9, 4.8))
        if chart == "scatter":
            if groups:
                for name, color in zip(groups, SERIES_COLORS):
                    part = data[g == name]
                    ax.scatter(part[col[x]], part[col[y]], s=28, alpha=.8, color=color, label=f"{name} ({len(part)})")
                ax.legend(frameon=False, fontsize=8)
            else:
                ax.scatter(data[col[x]], data[col[y]], s=28, alpha=.75, color=PALETTE[0])
            ax.set_xlabel(label[x]); ax.set_ylabel(label[y])
            if log and y != "year":
                ax.set_yscale("log")
            if log and x != "year":
                ax.set_xscale("log")
            out["correlation_spearman"] = round(float(data[col[x]].corr(data[col[y]], method="spearman")), 2)
        elif chart == "histogram":
            vals = data[col[x]]
            if log and x != "year":
                bins = np.logspace(np.log10(max(vals.min(), 1)), np.log10(vals.max() + 1), 20)
                ax.set_xscale("log")
            else:
                bins = 20 if x != "year" else range(int(vals.min()), int(vals.max()) + 2)
            ax.hist(vals, bins=bins, color=PALETTE[0], edgecolor="white")
            ax.set_xlabel(label[x]); ax.set_ylabel("Datasets")
        else:
            if not groups:
                g, groups = pd.Series("All", index=data.index), ["All"]
            series = [data.loc[g == name, col[x]] for name in groups]
            ax.boxplot(series, labels=[f"{n}\n(n={len(v)})" for n, v in zip(groups, series)], patch_artist=True,
                       boxprops={"facecolor": PALETTE[1]}, medianprops={"color": "#123B4A"})
            ax.set_ylabel(label[x])
            if log and x != "year":
                ax.set_yscale("log")
            ax.tick_params(axis="x", labelsize=8)
            out["medians"] = {str(n): float(v.median()) for n, v in zip(groups, series)}
        from matplotlib.ticker import MaxNLocator
        if x == "year" and chart != "box":
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        if (chart == "scatter" and y == "year") or (chart == "box" and x == "year"):
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        v = data[col[x]]
        out["summary_" + x] = {"min": float(v.min()), "median": float(v.median()), "max": float(v.max())}
        ax.set_title(title or {"scatter": f"{label[x]} vs {label.get(y, '')}", "histogram": f"Distribution of {label[x].lower()}",
                               "box": f"{label[x]} by {(group_by or 'all').replace('_', ' ')}"}[chart],
                     color="#123B4A", fontsize=12, fontweight="bold", loc="left")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        self.images.append(_fig_to_b64(fig))
        out["chart"] = "shown to the user"
        return out

    def summarize_category(self, category="All", **_):
        df = self.df if category in (None, "All") else self.df[self.df["category"] == category]
        if not len(df):
            return {"error": f"Unknown category. Choose one of: {', '.join(self.categories)}"}
        years = df["_year"].dropna()
        subj = df["_subjects"].dropna()
        top = lambda col, n: {k: int(v) for k, v in df[col].explode().dropna().value_counts().head(n).items()}
        newest = df.sort_values("_year", ascending=False).head(5)
        return {
            "category": category, "datasets": len(df),
            "year_range": [int(years.min()), int(years.max())] if len(years) else None,
            "datasets_since_2023": int((years >= 2023).sum()),
            "top_diseases": {k: v for k, v in top("_dis", 11).items() if k != "Healthy"},
            "healthy_cohort_datasets": int(df["_dis"].map(lambda ts: "Healthy" in ts).sum()),
            "modalities": top("_mods", 8),
            "access": {k: int(v) for k, v in df["_access"].value_counts().items()},
            "with_segmentation_masks": int((df["_segmentation_mask"] == "yes").sum()),
            "with_healthy_controls": int((df["_healthy_control"] == "yes").sum()),
            "subjects": {"median": float(subj.median()), "largest": float(subj.max())} if len(subj) else None,
            "newest_datasets": [f"{r['dataset_name']} ({int(r['_year']) if pd.notna(r['_year']) else 'n/a'})" for _, r in newest.iterrows()],
        }

    # ------------------------------------------------------------------ sandboxed python
    _BANNED_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "getattr", "setattr",
                     "delattr", "input", "breakpoint", "exit", "quit", "help", "memoryview", "type", "object", "super", "format",
                     "classmethod", "staticmethod", "property"}
    _BANNED_ATTRS = re.compile(r"^(_.*|read_.*|to_(csv|excel|json|pickle|parquet|feather|hdf|sql|html|latex|clipboard|stata|gbq|markdown|xml|orc)|"
                               r"savefig|imsave|eval|query|system|popen|load.*|save.*|fromfile|tofile|genfromtxt|memmap|DataSource|"
                               r"format|format_map|os|sys|subprocess|builtins|importlib|io|common|compat|util|testing|ctypes)$")

    _MODULES = {"pandas": pd, "numpy": np, "matplotlib.pyplot": plt, "matplotlib": matplotlib, "math": math,
                "collections": collections, "statistics": statistics}
    try:
        import seaborn as _sns
        _MODULES["seaborn"] = _sns
    except ImportError:
        pass

    def _analysis_frame(self):
        """Copy of the data where the main columns hold clean values, so straightforward model code is correct
        (e.g. df['access_type'] == 'Open' must match "Open (CC BY 4.0)" too). Original text is kept in <col>_details."""
        f = self.df.drop(columns=["_text"]).copy()
        yn = {"yes": "Yes", "no": "No", "ns": "Not specified"}
        for col in ["year", "subject_no", "access_type", "modality", "disease", "country", "format"] + YES_NO_FIELDS:
            f[col + "_details"] = f[col]
        f["year"], f["subject_no"], f["access_type"] = f["_year"], f["_subjects"], f["_access"]
        for col, parsed in (("modality", "_mods"), ("disease", "_dis"), ("country", "_ctry"), ("format", "_fmt")):
            f[col] = f[parsed].map(", ".join)
        for col in YES_NO_FIELDS:
            f[col] = f["_" + col].map(yn)
        return f

    def run_python(self, code="", **_):
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            return {"error": f"SyntaxError: {e}"}
        # Imports of a few safe modules are allowed (models write them out of habit); they are resolved here,
        # never through the real import machinery.
        imported = {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name not in self._MODULES:
                        return {"error": f"Not allowed in the sandbox: import {a.name}. Available: pd, np, plt, sns, math, collections, statistics"}
                    imported[a.asname or a.name.split(".")[0]] = self._MODULES[a.name if a.asname else a.name.split(".")[0]]
            elif isinstance(node, ast.ImportFrom):
                mod = self._MODULES.get(node.module or "")
                if mod is None:
                    return {"error": f"Not allowed in the sandbox: from {node.module} import ..."}
                for a in node.names:
                    if (a.name.startswith("_") or not hasattr(mod, a.name) or self._BANNED_ATTRS.match(a.name)
                            or a.name in self._BANNED_NAMES or a.name == "*"):
                        return {"error": f"Not allowed in the sandbox: from {node.module} import {a.name}"}
                    imported[a.asname or a.name] = getattr(mod, a.name)
        tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        if any(isinstance(n, ast.Name) and n.id == "df" and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(tree)):
            return {"error": "Rejected: do not overwrite df; read from it and store results in other variables."}
        if not any(isinstance(n, ast.Name) and n.id == "df" and isinstance(n.ctx, ast.Load) for n in ast.walk(tree)):
            return {"error": "Rejected: the code must compute its results from df (the full database is in df, including "
                             "year and subject_no). Never type in, copy or simulate data."}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.While, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Await, ast.Yield, ast.YieldFrom)):
                return {"error": f"Not allowed in the sandbox: {type(node).__name__}"}
            if isinstance(node, ast.Name) and node.id in self._BANNED_NAMES:
                return {"error": f"Not allowed in the sandbox: {node.id}"}
            if isinstance(node, ast.Attribute) and self._BANNED_ATTRS.match(node.attr) and node.attr not in ("_mods", "_dis", "_fmt", "_ctry", "_access", "_segmentation_mask", "_healthy_control", "_year", "_subjects"):
                return {"error": f"Not allowed in the sandbox: .{node.attr}"}
        safe_builtins = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k) for k in (
            "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance", "len",
            "list", "map", "max", "min", "print", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip")}
        env = {"__builtins__": safe_builtins, "df": self._analysis_frame(), "pd": pd, "np": np, "plt": plt,
               "sns": self._MODULES.get("seaborn"), **imported}
        plt.close("all")
        stdout = io.StringIO()
        try:
            body, last = tree.body, None
            if body and isinstance(body[-1], ast.Expr):
                last = ast.Expression(body.pop().value)
            with contextlib.redirect_stdout(stdout):
                exec(compile(ast.Module(body=body, type_ignores=[]), "<agent>", "exec"), env)
                value = eval(compile(last, "<agent>", "eval"), env) if last else env.get("result")
        except Exception as e:
            plt.close("all")
            return {"error": f"{type(e).__name__}: {e}"}
        out = {}
        if plt.get_fignums():
            fig = plt.gcf()
            if fig.get_axes():
                self.images.append(_fig_to_b64(fig))
                out["chart"] = "shown to the user"
            plt.close("all")
        if type(value).__module__.startswith("matplotlib"):
            value = None  # an Axes/Figure object: the chart itself is attached above
        if isinstance(value, pd.DataFrame):
            if {"dataset_name"}.issubset(value.columns) and len(value):
                cols = [c for c in ["category"] + COLUMNS if c in value.columns]
                self.tables.append((f"{len(value)} datasets", value[cols].reset_index(drop=True)))
            value = value.head(30).to_string(max_colwidth=60)
        elif isinstance(value, pd.Series):
            value = value.head(40).to_string()
        if value is not None:
            out["result"] = _short(value, 4000)
        printed = stdout.getvalue()
        if printed:
            out["printed"] = _short(printed, 3000)
        return out or {"result": "Code ran without output. Assign the answer to `result`."}

    # ------------------------------------------------------------------ argument repair
    @staticmethod
    def _coerce(value, spec):
        """Repair common argument mistakes of smaller models: lists sent as JSON text, a list where one value is
        expected, wrong case in enum values, numbers or booleans as strings."""
        if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
            try:
                value = json.loads(value)
            except ValueError:
                pass
        kind = spec.get("type")
        if kind == "array":
            if isinstance(value, str):
                value = [v.strip() for v in re.split(r"[,;]", value) if v.strip()]
            elif not isinstance(value, list):
                value = [value]
            enum = spec.get("items", {}).get("enum")
            if enum:
                lookup = {str(e).lower(): e for e in enum}
                value = [lookup.get(str(v).lower(), v) for v in value]
            return [str(v) for v in value]
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            return None
        if kind == "integer":
            m = re.search(r"-?\d+", str(value))
            return int(m.group(0)) if m else None
        if kind == "boolean":
            return value if isinstance(value, bool) else str(value).strip().lower() in ("true", "yes", "1")
        if "enum" in spec:
            lookup = {str(e).lower(): e for e in spec["enum"]}
            v = str(value).strip().lower()
            return lookup.get(v, lookup.get({"true": "yes", "false": "no"}.get(v, v), value))
        return str(value)

    # ------------------------------------------------------------------ dispatch
    def call(self, name, raw_args):
        fn = {"search_datasets": self.search_datasets, "get_dataset_details": self.get_dataset_details,
              "count_datasets": self.count_datasets, "summarize_category": self.summarize_category,
              "numeric_chart": self.numeric_chart,
              "run_python": self.run_python}.get(name)
        if fn is None:
            return {"error": f"Unknown tool '{name}'."}
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args.strip() else (raw_args or {})
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except Exception as e:
            return {"error": f"Invalid arguments ({e}). Send a JSON object."}
        props = next(t["function"]["parameters"]["properties"] for t in self.schemas() if t["function"]["name"] == name)
        unknown = [k for k in args if k not in props]
        args = {k: self._coerce(v, props[k]) for k, v in args.items() if k in props and v is not None}
        for k, v in args.items():  # reject values outside an enum instead of silently doing something else
            allowed = props[k].get("enum") or props[k].get("items", {}).get("enum")
            bad = [x for x in (v if isinstance(v, list) else [v]) if allowed and x not in allowed]
            if bad:
                return {"error": f"Invalid value {bad[0]!r} for '{k}'. Allowed: {', '.join(map(str, allowed))}"}
        missing = [k for k in next(t["function"]["parameters"].get("required", []) for t in self.schemas()
                                   if t["function"]["name"] == name) if k not in args]
        if missing:
            return {"error": f"Missing required argument(s): {', '.join(missing)}"}
        try:
            result = fn(**args)
            if unknown and isinstance(result, dict):
                result["ignored_arguments"] = unknown
            return result
        except TypeError as e:
            return {"error": f"Bad arguments: {e}"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
