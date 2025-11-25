import os
import re
import json
import uuid
import pathlib
from typing import List, Tuple, Dict, Any

import streamlit as st
from dotenv import load_dotenv

# --- Local Imports ---
# Import the new Firebase functions from firebase_auth
from src.firebase_auth import (
    load_conversations_from_firestore, 
    save_conversations_to_firestore,
    get_user_data
)

# ---------------- Session helpers ----------------
def _new_session(name="New Chat"):
    return {"name": name, "history": []}

def create_new_chat(convos: dict) -> str:
    """Creates a new chat, adds it to convos, and saves to Firestore if logged in."""
    sid = str(uuid.uuid4())[:8]
    convos[sid] = _new_session("New Chat")
    save_convos()
    return sid

def save_convos():
    """
    Saves the current state of conversations to Firestore IF user is logged in.
    """
    if st.session_state.get('logged_in') and st.session_state.get('user_info'):
        uid = st.session_state.user_info.get("localId")
        if uid:
            save_conversations_to_firestore(uid, st.session_state.convos)

def ensure_session_state():
    """
    Initializes all core session state keys with default values.
    Actual data loading is deferred to 'load_user_data_from_firestore' after login.
    """
    if "convos" not in st.session_state:
        st.session_state.convos = {}
    if "active_id" not in st.session_state:
        st.session_state.active_id = None
    if "renaming" not in st.session_state:
        st.session_state.renaming = False
    if "confirming_delete" not in st.session_state:
        st.session_state.confirming_delete = False
    if "ui_theme" not in st.session_state:
        st.session_state.ui_theme = "dark"
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "password_question_count" not in st.session_state:
        st.session_state.password_question_count = 0
    if "phishing_question_count" not in st.session_state:
        st.session_state.phishing_question_count = 0
    if "in_password_game" not in st.session_state:
        st.session_state.in_password_game = False

    # Ensure a chat exists for UI when not logged in, or if logged in but no data loaded yet
    if not st.session_state.convos:
        new_id = create_new_chat(st.session_state.convos)
        st.session_state.active_id = new_id
    
    if st.session_state.active_id not in st.session_state.convos:
        st.session_state.active_id = next(iter(st.session_state.convos))

def load_user_data_from_firestore():
    """
    Called ONCE immediately after a successful login to load user data and conversations.
    """
    uid = st.session_state.user_info.get("localId")
    if not uid:
        return

    # 1. Load user profile data (like username)
    user_data = get_user_data(uid)
    if user_data:
        st.session_state.user_info.update(user_data) 

    # 2. Load conversations
    convos = load_conversations_from_firestore(uid)
    st.session_state.convos = convos
    
    # 3. Set active chat
    if convos:
        st.session_state.active_id = next(iter(convos))
    else:
        new_id = create_new_chat(st.session_state.convos)
        st.session_state.active_id = new_id

def active_session():
    if st.session_state.active_id not in st.session_state.convos:
        if st.session_state.convos:
            st.session_state.active_id = next(iter(st.session_state.convos))
        else:
            new_id = create_new_chat(st.session_state.convos)
            st.session_state.active_id = new_id
            
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