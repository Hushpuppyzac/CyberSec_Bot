import streamlit as st
import requests
import json
import re 
from src.firebase_auth import create_user_in_db
from src.data_loader import load_user_data_from_firestore

# --- Password Validation & Strength Logic ---
def get_password_strength(password: str) -> dict:
    """
    Analyzes password and returns a score (0-4), a color, and a feedback message.
    """
    score = 0
    feedback = []
    
    # Check 1: Length
    if len(password) >= 8:
        score += 1
    else:
        feedback.append("At least 8 characters")
        
    # Check 2: Case
    if re.search(r'[a-z]', password) and re.search(r'[A-Z]', password):
        score += 1
    else:
        feedback.append("Lower & Uppercase letters")
        
    # Check 3: Numbers
    if re.search(r'\d', password):
        score += 1
    else:
        feedback.append("At least one number")
        
    # Check 4: Symbols
    if re.search(r'[^\w\s]', password):
        score += 1
    else:
        feedback.append("At least one symbol (!@#$...)")
        
    # Only say "Enter a password" if the input is truly empty
    if len(password) == 0:
        return {"score": 0, "color": "red", "msg": "Enter a password"}
    
    # If score is low (even 0), show the feedback list
    elif score < 3:
        return {"score": score, "color": "red", "msg": "Weak: " + ", ".join(feedback)}
        
    elif score == 3:
        return {"score": score, "color": "orange", "msg": "Moderate: " + ", ".join(feedback)}
        
    else:
        return {"score": 4, "color": "green", "msg": "Strong! ✅"}

def show_login_page(auth, show_theme_selector):
    st.title("Welcome to CyCore")
    st.caption("Your personal AI cybersecurity tutor. Please log in or sign up to continue.")

    show_theme_selector()
    st.divider()

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        login_button = st.button("Login", key="login_button", use_container_width=True)

        if login_button:
            if email and password:
                try:
                    user = auth.sign_in_with_email_and_password(email, password)
                    st.session_state.logged_in = True
                    st.session_state.user_info = user
                    load_user_data_from_firestore() 
                    st.rerun()
                except requests.exceptions.HTTPError as e:
                    try:
                        error_json = e.response.json()
                        message = "Invalid email or password." 
                    except (AttributeError, json.JSONDecodeError):
                        message = "Invalid email or password."
                    st.error(message)
            else:
                st.error("Please enter both email and password.")

    with signup_tab:
        new_email = st.text_input("Email", key="signup_email")
        
        # We use 'on_change' or just rely on Streamlit's rerun loop to update the UI
        new_password = st.text_input("Password", type="password", key="signup_password")
        
        # --- PASSWORD STRENGTH METER ---
        if new_password:
            strength = get_password_strength(new_password)
            
            # 1. Visual Progress Bar
            # We map score 0-4 to a progress value 0-100
            st.progress(strength["score"] / 4, text=None)
            
            # 2. Colored Text Feedback
            st.markdown(
                f"<small style='color:{strength['color']};'>**Strength:** {strength['msg']}</small>", 
                unsafe_allow_html=True
            )
        # -------------------------------

        confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm_password")
        new_username = st.text_input("Username", key="signup_username")
        signup_button = st.button("Sign Up", key="signup_button", use_container_width=True)

        if signup_button:
            if new_email and new_username and new_password and confirm_password:
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                    return
                
                # Final strict validation check before creating account
                final_check = get_password_strength(new_password)
                if final_check["score"] < 4:
                     st.error("Password is too weak. Please address the missing requirements shown above.")
                     return

                try:
                    user = auth.create_user_with_email_and_password(new_email, new_password)
                    uid = user['localId']
                    create_user_in_db(uid, new_email, new_username)
                    st.success("Account created! Please log in.")
                except requests.exceptions.HTTPError as e:
                    try:
                        error_json = e.response.json()
                        error_code = error_json.get("error", {}).get("message", "UNKNOWN_ERROR")
                        
                        if "EMAIL_EXISTS" in error_code or "INVALID_EMAIL" in error_code:
                            message = "Could not create account. Please ensure your email is valid and not already registered."
                        else:
                            message = error_code.replace("_", " ").title()
                            
                    except (AttributeError, json.JSONDecodeError):
                        message = "Could not create account, email already exists."
                    st.error(message)
            else:
                st.error("Please fill out all fields.")