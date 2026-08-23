from __future__ import annotations

import pandas as pd
import streamlit as st


def athletes_df(athletes):
    return pd.DataFrame(athletes)


def status_badge(ok: bool, text: str) -> None:
    if ok:
        st.success(text)
    else:
        st.error(text)
