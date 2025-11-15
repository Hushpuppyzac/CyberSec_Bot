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
from src.firebase_auth import get_auth

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
if current_theme == "light":
    # Directly inject the specific styles for the login button in light theme
    st.markdown(
        f"""
        <style>
        /* Specific override for the Login button in light theme */
        button.st-emotion-cache-1anq8dj.etdmgzm7 {{
            background: #000000 !important; /* Black background */
            color: #ffffff !important; /* White text */
            margin-top: 1rem !important;
            border: none !important;
            font-weight: 600 !important;
        }}
        button.st-emotion-cache-1anq8dj.etdmgzm7:hover {{
            background: #333333 !important; /* Slightly lighter black on hover */
            color: #ffffff !important;
        }}
        /* Ensure text inside the button also gets forced white color */
        button.st-emotion-cache-1anq8dj.etdmgzm7 p {{
            color: #ffffff !important;
            opacity: 1 !important;
        }}
        /* Ensure disabled state is visible */
        button.st-emotion-cache-1anq8dj.etdmgzm7:disabled,
        button.st-emotion-cache-1anq8dj.etdmgzm7:disabled p {{
          background: #616161 !important;
          color: #bdbdbd !important;
          opacity: 1 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )


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

# ---------------- Login / Signup UI ----------------
def show_login_ui():
    st.image("logo.png", width=140)
    st.title("Welcome to CyCore")
    st.caption("Your personal AI cybersecurity tutor. Please log in or sign up to continue.")
    
    show_theme_selector()
    st.markdown('<hr style="margin-top: 1.5rem; margin-bottom: 1rem; border-color: var(--border);">', unsafe_allow_html=True)

    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="your@email.com", key="login_email")
            password = st.text_input("Password", type="password", placeholder="••••••••••", key="login_password")
            login_submitted = st.form_submit_button("Login", use_container_width=True)
            
            if login_submitted:
                if not auth_handler:
                    st.error("Authentication service is not available.")
                    return
                try:
                    user = auth_handler.sign_in_with_email_and_password(email, password)
                    st.session_state['logged_in'] = True
                    st.session_state['user_info'] = user
                    st.rerun()
                except requests.exceptions.HTTPError as e:
                    message = "Invalid email or password."
                    try:
                        error_json = e.response.json()
                        message = error_json.get("error", {}).get("message", "UNKNOWN_ERROR").replace("_", " ").title()
                    except (AttributeError, json.JSONDecodeError):
                        pass
                    st.error(f"Login failed: {message}")

    with signup_tab:
        with st.form("signup_form"):
            email = st.text_input("Email", placeholder="your@email.com", key="signup_email_form")
            password = st.text_input("Password", type="password", placeholder="••••••••••", key="signup_password_form")
            signup_submitted = st.form_submit_button("Sign Up", use_container_width=True)
            if signup_submitted:
                if not auth_handler:
                    st.error("Authentication service is not available.")
                    return
                try:
                    user = auth_handler.create_user_with_email_and_password(email, password)
                    st.success("Account created! Please log in.")
                except requests.exceptions.HTTPError as e:
                    message = "Could not create account."
                    try:
                        error_json = e.response.json()
                        message = error_json.get("error", {}).get("message", "UNKNOWN_ERROR").replace("_", " ").title()
                    except (AttributeError, json.JSONDecodeError):
                        pass
                    st.error(f"Sign up failed: {message}")
                    
    st.markdown('</div>', unsafe_allow_html=True)

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
            convos.pop(active_id, None)
            st.session_state.active_id = next(iter(convos), None)
            if not st.session_state.active_id:
                new_id = create_new_chat(convos)
                st.session_state.active_id = new_id
            save_convos()
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

        # Sign Out Button at the bottom
        st.divider()
        if st.button("Sign Out", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state.pop('user_info', None)
            st.session_state.convos = {}
            st.session_state.active_id = None
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
    show_login_ui()
