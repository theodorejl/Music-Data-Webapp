"""Entry point: streamlit run app/Home.py

Deliberately tiny and never edited: everything else lives in app/shell.py and app/views/,
which are reloaded live (see app/devreload.py).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # make `core` and `app` importable (local and Streamlit Cloud)
    sys.path.insert(0, str(ROOT))

from app.devreload import refresh_modules  # noqa: E402

refresh_modules()  # one consistent version of the whole code after any edit

import streamlit as st  # noqa: E402

from app.devreload import watch  # noqa: E402

st.set_page_config(page_title="DatAtlaSonore", page_icon=str(ROOT / "app" / "assets" / "mark.svg"), layout="wide")
watch()  # before anything that could fail mid-edit, so the next save always repairs the page

from app import shell  # noqa: E402

shell.run()
