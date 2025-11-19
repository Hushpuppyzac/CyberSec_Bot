import re
import streamlit as st
from src.session import save_convos
from typing import List, Tuple

_STOPWORDS = {
    "what","how","why","is","are","the","a","an","of","in","to","for","on","with","and","or",
    "my","your","our","their","this","that","it","do","does","can","should","could","about",
    "please","tell","me","explain"
}

OFFTOPIC_SUFFIX = " (Not Cybersecurity Related)"

def _clean_title(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    words = [w for w in text.split() if w not in _STOPWORDS]
    return " ".join(words[:6]).title() or "Chat"

def _ensure_unique_name(name: str, convos: dict) -> str:
    existing = {v["name"] for v in convos.values()}
    if name not in existing:
        return name
    n = 2
    while True:
        candidate = f"{name} ({n})"
        if candidate not in existing:
            return candidate
        n += 1

def set_title_from_msgs(client, model: str, convos: dict, session_id: str, user_msgs: list[str]):
    if not user_msgs:
        return
    sess = convos[session_id]
    default_names = {"New Chat", "New chat"}
    if not (sess["name"] in default_names or sess["name"].startswith("Chat ")):
        return

    title = None
    if client:
        try:
            prompt = (
                "Create a concise 4–6 word title for this conversation topic. "
                "No punctuation, quotes, emojis, or IDs. Return title only.\n\n"
                f"User messages:\n- " + "\n- ".join(user_msgs[:2])
            )
            resp = client.models.generate_content(model=model, contents=prompt)
            if resp and resp.text:
                t = resp.text.strip().replace("\n", " ")
                t = re.sub(r'["""\.\!\?\:]', "", t)
                title = t
        except Exception:
            title = None

    if not title:
        title = _clean_title(" ".join(user_msgs[:2]))

    title = title[:40].strip()
    sess["name"] = _ensure_unique_name(title, convos)
    save_convos()

def auto_title_if_needed(client, model: str, convos: dict, session_id: str):
    sess = convos[session_id]
    name = sess["name"]
    default_names = {"New Chat", "New chat"}
    if not (name in default_names or name.startswith("Chat ")):
        return
    user_msgs = [m for (r, m) in sess["history"] if r == "user"][:2]
    if not user_msgs:
        return
    set_title_from_msgs(client, model, convos, session_id, user_msgs)

def _maybe_update_title_after_first_turn(client, model: str):
    """De-duplicated helper to update the conversation title on the first/second user turn."""
    u_turns = [m for (r, m) in st.session_state.convos[st.session_state.active_id]["history"] if r == "user"]
    if len(u_turns) in (1, 2):
        old_name = st.session_state.convos[st.session_state.active_id]["name"]
        auto_title_if_needed(client, model, st.session_state.convos, st.session_state.active_id)
        new_name = st.session_state.convos[st.session_state.active_id]["name"]
        if old_name != new_name:
            st.rerun()

def mark_offtopic(client, model, convos: dict, session_id: str):
    sess = convos[session_id]
    name = sess["name"]

    if name.lower().startswith("new chat") or name.startswith("Chat "):
        user_msgs = [m for (r, m) in sess["history"] if r == "user"][-2:]
        if user_msgs:
            set_title_from_msgs(client, model, convos, session_id, user_msgs)
            name = sess["name"]

    if not name.endswith(OFFTOPIC_SUFFIX):
        sess["name"] = _ensure_unique_name(name + OFFTOPIC_SUFFIX, convos)
        save_convos()

def build_prompt(system_instruction:str, user_msg: str, history: List[Tuple[str, str]]) -> str:
    convo = [f"System: {system_instruction}"]
    for role, msg in history[-8:]:
        convo.append(("User: " if role == "user" else "Tutor: ") + msg)
    convo.append(f"User: {user_msg}")
    convo.append("Tutor:")
    return "\n".join(convo)
