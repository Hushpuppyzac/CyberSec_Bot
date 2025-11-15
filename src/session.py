import os
import re
import json
import uuid
import pathlib
from typing import List, Tuple

import streamlit as st
from dotenv import load_dotenv

# ---------------- Config ----------------
load_dotenv()
IS_PUBLIC = os.getenv("PUBLIC_DEPLOY", "0") == "1"
DATA_FILE = pathlib.Path("convos.json") if not IS_PUBLIC else None

# ---------------- Session helpers ----------------
def _new_session(name="New Chat"):
    return {"name": name, "history": []}

def create_new_chat(convos: dict) -> str:
    sid = str(uuid.uuid4())[:8]
    convos[sid] = _new_session("New Chat")
    return sid

def load_convos():
    if DATA_FILE is None:
        # Public: keep everything in-memory per session only
        sid = str(uuid.uuid4())[:8]
        return {sid: _new_session("New Chat")}
    # private/local: existing behavior
    if DATA_FILE.exists():
        try:
            obj = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and obj:
                for _, sess in obj.items():
                    sess["history"] = [(r, m) for r, m in sess.get("history", [])]
                return obj
        except Exception:
            try:
                DATA_FILE.rename(DATA_FILE.with_suffix(".bak"))
            except Exception:
                pass
    sid = str(uuid.uuid4())[:8]
    return {sid: _new_session("New Chat")}

def save_convos():
    if DATA_FILE is None:
        return  # Public: don't persist to disk
    DATA_FILE.write_text(
        json.dumps(st.session_state.convos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def ensure_session_state():
    if "convos" not in st.session_state:
        st.session_state.convos = load_convos()
    if not st.session_state.convos:
        create_new_chat(st.session_state.convos)
    if "active_id" not in st.session_state:
        st.session_state.active_id = next(iter(st.session_state.convos))
    if st.session_state.active_id not in st.session_state.convos:
        st.session_state.active_id = next(iter(st.session_state.convos))
    if "renaming" not in st.session_state:
        st.session_state.renaming = False
    if "ui_theme" not in st.session_state:
        st.session_state.ui_theme = "dark"

def active_session():
    return st.session_state.convos[st.session_state.active_id]

def active_history() -> List[Tuple[str, str]]:
    return active_session()["history"]

def set_active_history(h: List[Tuple[str, str]]):
    active_session()["history"] = h
    save_convos()

def append_msg(role: str, msg: str):
    h = active_history()
    h.append((role, msg))
    set_active_history(h)

def find_empty_chat(convos: dict):
    for sid, sess in convos.items():
        if not sess.get("history"):
            return sid
    return None
