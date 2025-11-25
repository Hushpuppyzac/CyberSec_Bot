import os
import re
import json
import uuid
import pathlib
import random
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
from src.game import handle_password_game

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
        st.markdown("</div>", unsafe_allow_html=True)

        # --- 1. CONFIRMATION MODE (Triggers only when Delete is clicked) ---
        if st.session_state.get("confirming_delete", False):
            st.warning("Delete this chat?")
            
            # Keep Yes/Cancel side-by-side so it looks neat
            col_yes, col_no = st.columns(2)
            
            with col_yes:
                if st.button("Yes", type="primary", use_container_width=True):
                    # --- DELETION LOGIC ---
                    uid = st.session_state.user_info.get("localId")
                    if uid:
                        delete_conversation_from_firestore(uid, active_id)
                    
                    convos.pop(active_id, None)
                    st.session_state.active_id = next(iter(convos), None)
                    if not st.session_state.active_id:
                        new_id = create_new_chat(convos)
                        st.session_state.active_id = new_id
                    
                    save_convos()
                    st.session_state.confirming_delete = False 
                    st.toast("🗑️ Chat deleted", icon="✅")
                    st.rerun()

            with col_no:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.confirming_delete = False
                    st.rerun()

        # --- 2. NORMAL MODE (Vertical Stack, Natural Width) ---
        else:
            # 1. New Chat Button
            # Removing 'use_container_width=True' makes it look like your screenshot
            if st.button("➕ New"):
                if find_empty_chat(convos):
                    st.toast("Empty chat exists.", icon="ℹ️")
                else:
                    new_id = create_new_chat(convos)
                    st.session_state.active_id = new_id
                    save_convos()
                    st.toast("New chat created", icon="✨")
                st.rerun()
            
            # 2. Rename Button
            if st.button("✏️ Rename"):
                st.session_state.renaming = True
                st.rerun()
            
            # 3. Delete Button (Triggers Confirmation)
            if st.button("🗑️ Delete"):
                st.session_state.confirming_delete = True
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
        history = active_history()
        if (
            user_msg.lower() == "yes"
            and len(history) > 0
            and history[-1][0] == "assistant"
            and "would you like to play a game" in history[-1][1].lower()
        ):
            st.session_state.in_password_game = True
            handle_password_game(user_msg)
            st.rerun()

        if st.session_state.get("in_password_game"):
            handle_password_game(user_msg)
            st.rerun()

        if "password" in user_msg.lower():
            st.session_state.password_question_count += 1
        
        if "phishing" in user_msg.lower():
            st.session_state.phishing_question_count += 1

        if not st.session_state.get("in_password_game"):
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

            # ---------------------------------------------------------
            # Logic to Trigger the Password Quiz Game
            # ---------------------------------------------------------
            # 1. Save the Main Assistant Response FIRST
            append_msg("assistant", collected)

            # 2. Logic to Trigger the Game
            trigger_game = False
            
            # Condition A: Explicit request (Checking synonyms for "improve")
            # This catches: "make it better", "more secure", "stronger", "strengthen", etc.
            improve_keywords = ["improve", "better", "secure", "strong", "safe", "strengthen"]
            
            if "password" in user_msg.lower() and any(k in user_msg.lower() for k in improve_keywords):
                trigger_game = True
                
            # Condition B: Randomly trigger after the 2nd OR 3rd question
            # - If count is >= 3, it triggers automatically (guaranteed).
            # - If count is 2, we flip a coin (50% chance) to trigger early.
            elif st.session_state.password_question_count >= 3 or \
                 (st.session_state.password_question_count == 2 and random.choice([True, False])):
                trigger_game = True

            # 3. If Triggered, Send the Prompt as a NEW Message
            if trigger_game and st.session_state.get("in_password_game") is not True:
                
                # OPTIONAL: Debug Toast
                # st.toast("Triggering Password Game... 🎮", icon="🕹️")
                
                game_msg = "\n\nWould you like to play a game to better understand what makes a strong password?"
                append_msg("assistant", game_msg)
                
                # Reset the counter
                st.session_state.password_question_count = 0

            # ---------------------------------------------------------
            # Logic to Trigger the Phishing Quiz Link
            # ---------------------------------------------------------
            trigger_phishing = False
            
            # 1. Keywords for explicit request
            phishing_test_keywords = ["test", "quiz", "check", "practice", "game", "spot", "identify"]
            
            # Condition A: Explicit request
            if "phishing" in user_msg.lower() and any(k in user_msg.lower() for k in phishing_test_keywords):
                trigger_phishing = True
                
            # Condition B: Randomly trigger after the 2nd OR 3rd question about phishing
            elif st.session_state.phishing_question_count >= 3 or \
                 (st.session_state.phishing_question_count == 2 and random.choice([True, False])):
                trigger_phishing = True
            
            if trigger_phishing:
                # We send the link as a separate message bubble so it stands out
                quiz_msg = (
                    "\n\n**(⚠️ Safety Reminder)**: As a general rule, **please do not click on random links** you receive online.\n\n"
                    "However, for this exercise, I am sharing a **genuine, verified link from Google** specifically designed to test your phishing skills:\n"
                    "👉 https://phishingquiz.withgoogle.com/"
                )
                append_msg("assistant", quiz_msg)
                
                # Reset the counter so we don't annoy the user
                st.session_state.phishing_question_count = 0
            
            # ---------------------------------------------------------

            _maybe_update_title_after_first_turn(client, MODEL)
            st.rerun()

# ---------------- App Entry Point ----------------
if st.session_state.get('logged_in'):
    show_chatbot_ui()
else:
    inject_file("assets/login_page_header_styles.css") # Inject login page specific styles
    show_login_page(auth_handler, show_theme_selector)
