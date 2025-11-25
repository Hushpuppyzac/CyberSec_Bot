import streamlit as st
from src.firebase_auth import get_user_data, load_conversations_from_firestore
from src.session import create_new_chat

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
