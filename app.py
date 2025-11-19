import os
import re
import json
import uuid
import pathlib
from typing import List, Tuple
import requests.exceptions

import streamlit as st
from dotenv import load_dotenv
from google import genai

# --- Local Imports ---
from src.session import (
    ensure_session_state,
    active_history,
    append_msg,
    create_new_chat,
    save_convos,
    find_empty_chat
)
from src.guards import guardrails_or_offtopic
from src.llm import (
    build_prompt,
    _maybe_update_title_after_first_turn,
    mark_offtopic
)
from src.firebase_auth import get_auth, delete_conversation_from_firestore
from src.login import show_login_page

# ---------------- App Config ----------------
load_dotenv()
st.set_page_config(page_title="CyCore", page_icon="🛡️", layout="wide")
ensure_session_state()

# ---------------- Firebase & Gemini Clients ----------------
auth_handler = get_auth()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.0-flash"
SYSTEM_INSTRUCTION = (
    "You are a friendly cybersecurity tutor for beginners and intermediate learners. "
    "Teach defensive security concepts including: passwords, phishing, 2FA, privacy, device hygiene, "
    "honeypots (defensive decoy systems), firewalls, intrusion detection, threat monitoring, and incident response. "
    "You can explain how attacks work from a defensive learning perspective (to help users understand threats), "
    "but refuse to teach actual hacking techniques, exploit code, or illegal activities. "
    "Use clear, short paragraphs and end with 1–2 actionable tips."
)
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ---------------- Asset Injection ----------------
def inject_file(file_path: str):
    p = pathlib.Path(file_path)
    with p.open("r", encoding="utf-8") as f:
        content = f.read()
    st.markdown(f"<style>{content}</style>", unsafe_allow_html=True)

def inject_theme(mode: str = "dark"):
    inject_file(f"assets/{mode}_theme.css")

# Inject all CSS globally on every run
current_theme = st.session_state.get("ui_theme", "dark")
inject_theme(current_theme)
inject_file("assets/style.css") # Inject general styles first

# ---------------- Reusable UI Components ----------------
def show_theme_selector():
    is_dark = st.session_state.ui_theme == "dark"
    new_mode_str = st.radio(
        "Theme", ["Dark", "Light"],
        horizontal=True,
        index=0 if is_dark else 1,
        key="theme_selector"
    )
    new_mode = "dark" if new_mode_str == "Dark" else "light"
    if new_mode != st.session_state.ui_theme:
        st.session_state.ui_theme = new_mode
        st.rerun()

# ---------------- Main Chatbot Application UI ----------------
def show_chatbot_ui():
    # --- Sidebar / Navigation UI ---
    with st.sidebar:
        st.image("logo.png", width=140)
        st.markdown("## 🛡️ CyCore")
        st.caption("Defensive Cybersecurity Guidance Only.")
        st.divider()
        
        show_theme_selector()
        st.divider()

        convos = st.session_state.convos
        active_id = st.session_state.active_id
        ids = list(convos.keys())

        st.markdown("**Conversations**")
        if ids:
            try:
                idx = ids.index(active_id)
            except ValueError:
                idx = 0
                st.session_state.active_id = ids[idx]
            
            chosen_index = st.radio(
                "Select conversation", options=range(len(ids)), index=idx,
                label_visibility="collapsed", key="conv_radio",
                format_func=lambda i: convos[ids[i]]["name"],
            )
            if ids[chosen_index] != active_id:
                st.session_state.active_id = ids[chosen_index]
                st.rerun()
        else:
            new_id = create_new_chat(convos)
            st.session_state.active_id = new_id
            save_convos()
            st.rerun()

        st.divider()
        st.markdown("**Manage**")
        st.markdown("<div class='sidebar-manage'>", unsafe_allow_html=True)
        new_clicked, rename_clicked, del_clicked = st.button("➕ New"), st.button("✏️ Rename"), st.button("🗑️ Delete")
        st.markdown("</div>", unsafe_allow_html=True)

        if new_clicked:
            if find_empty_chat(convos):
                st.toast("ℹ️ You already have an empty chat.", icon="✍️")
            else:
                new_id = create_new_chat(convos)
                st.session_state.active_id = new_id
                save_convos()
                st.toast("🆕 Created a new chat", icon="✨")
            st.rerun()

        if rename_clicked:
            st.session_state.renaming = True

        if del_clicked:
            # Get the uid before popping the conversation from session state
            uid = st.session_state.user_info.get("localId")
            if uid:
                delete_conversation_from_firestore(uid, active_id) # Delete from Firestore
            
            convos.pop(active_id, None)
            st.session_state.active_id = next(iter(convos), None)
            if not st.session_state.active_id:
                new_id = create_new_chat(convos)
                st.session_state.active_id = new_id
            save_convos() # Re-save all conversations to update Firestore (needed if new empty chat was created)
            st.toast("🗑️ Chat deleted", icon="✅")
            st.rerun()

        if st.session_state.get("renaming"):
            new_name = st.text_input("New name", value=convos[active_id]["name"])
            c1, c2 = st.columns(2)
            if c1.button("Save", use_container_width=True):
                convos[active_id]["name"] = new_name.strip() or convos[active_id]["name"]
                st.session_state.renaming = False
                save_convos()
                st.rerun()
            if c2.button("Cancel", use_container_width=True):
                st.session_state.renaming = False
                st.rerun()

        # --- User profile and Sign Out button ---
        st.divider()
        col1, col2, col3 = st.columns([1, 3, 2])
        
        with col1:
            st.image("logo.png", width=48) # Using app logo as profile pic
        
        with col2:
            username = st.session_state.user_info.get('username', 'User')
            st.markdown(f"**{username}**")
        
        with col3:
            if st.button("Sign Out", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.pop('user_info', None)
                st.session_state.pop('login_password_prev', None)
                st.session_state.pop('signup_password_prev', None)
                
                # Clear conversation state
                st.session_state.pop('convos', None)
                st.session_state.pop('active_id', None) 
                
                st.rerun()

    # --- Main Chat Area ---
    st.title("🛡️ CyCore")
    st.caption("Ask about any cybersecurity topic you wish to learn about.")

    for role, msg in active_history():
        with st.chat_message("user" if role == "user" else "assistant", avatar="👤" if role == "user" else "🛡️"):
            st.markdown(msg)

    if user_msg := st.chat_input("Message CyCore…"):
        redirect = guardrails_or_offtopic(user_msg, active_history())
        if redirect:
            append_msg("user", user_msg)
            append_msg("assistant", redirect)
            mark_offtopic(client, MODEL, st.session_state.convos, st.session_state.active_id)
            st.rerun()

        append_msg("user", user_msg)
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_msg)
        
        with st.chat_message("assistant", avatar="🛡️"):
            placeholder, collected = st.empty(), ""
            try:
                if not client:
                    raise ValueError("Gemini API client not initialized.")
                prompt = build_prompt(SYSTEM_INSTRUCTION, user_msg, active_history())
                stream = client.models.generate_content_stream(model=MODEL, contents=prompt)
                for ev in stream:
                    if hasattr(ev, "text") and ev.text:
                        collected += ev.text
                        placeholder.markdown(collected)
            except Exception as e:
                collected = f"⚠️ An error occurred: {e}"
                placeholder.markdown(collected)
        
        append_msg("assistant", collected)
        _maybe_update_title_after_first_turn(client, MODEL)

# ---------------- App Entry Point ----------------
if st.session_state.get('logged_in'):
    show_chatbot_ui()
else:
    inject_file("assets/login_page_header_styles.css") # Inject login page specific styles
    show_login_page(auth_handler, show_theme_selector)
