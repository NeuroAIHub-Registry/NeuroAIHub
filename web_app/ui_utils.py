import re

import pandas as pd
import streamlit as st

from data_utils import split_terms

displaying_columns = [
    "category", "dataset_name", "doi", "url", "year", "access_type",
    "institution", "country", "modality", "resolution", "subject_no",
    "slice_scan_no", "age_range", "acquisition_protocol", "format",
    "segmentation_mask", "preprocessing", "disease", "healthy_control",
    "staging_information", "clinical_data", "histopathology", "lab_data"
]

_URL = re.compile(r"https?://[^\s,;<>()]+")


def get_unique_options_from_column(df_column):
    """Sorted top-level values of a column; parenthesised details never split a value."""
    options = set()
    for value in df_column.dropna():
        options.update(split_terms(value))
    return sorted(options)


def _first_url(value):
    m = _URL.search(str(value))
    return m.group(0).rstrip(".)]") if m else None


def display_paginated_dataframe(df: pd.DataFrame, state_key: str, page_size: int = 5):
    """
    Renders a paginated dataframe with clickable links and number formatting.
    """
    if state_key not in st.session_state:
        st.session_state[state_key] = 1

    total_pages = max(1, (len(df) - 1) // page_size + 1)
    current_page = min(st.session_state[state_key], total_pages)
    start_index = (current_page - 1) * page_size
    end_index = start_index + page_size

    df_slice = df.iloc[start_index:end_index].copy()
    df_display = df_slice[[col for col in displaying_columns if col in df_slice.columns]].copy()

    # The url cell can hold several links plus notes; the link column needs a single URL.
    if "url" in df_display.columns:
        df_display["url"] = df_display["url"].map(_first_url)

    for col in ["year", "subject_no", "slice_scan_no"]:
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(
                lambda x: str(int(float(x))) if re.fullmatch(r"\d+(\.0+)?", str(x)) else str(x)
            )

    column_config = {
        "url": st.column_config.LinkColumn("URL", display_text="🔗 Link", width="small"),
    }

    st.dataframe(df_display, hide_index=True, use_container_width=True, column_config=column_config)

    if total_pages == 1:
        return
    c1, c2, c3, c4, c5 = st.columns([2, 2, 3, 2, 2])
    if c1.button("⏮️ First", key=f"first_{state_key}", disabled=(current_page == 1)):
        st.session_state[state_key] = 1; st.rerun()
    if c2.button("◀ Previous", key=f"prev_{state_key}", disabled=(current_page <= 1)):
        st.session_state[state_key] = current_page - 1; st.rerun()
    c3.markdown(f"<p style='text-align: center; margin-top: 8px;'>Page <b>{current_page}</b> of <b>{total_pages}</b></p>", unsafe_allow_html=True)
    if c4.button("Next ▶", key=f"next_{state_key}", disabled=(current_page >= total_pages)):
        st.session_state[state_key] = current_page + 1; st.rerun()
    if c5.button("Last ⏭️", key=f"last_{state_key}", disabled=(current_page == total_pages)):
        st.session_state[state_key] = total_pages; st.rerun()
