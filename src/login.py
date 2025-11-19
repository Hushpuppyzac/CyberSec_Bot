import streamlit as st
import requests
import json
import re # Added for password validation
from src.firebase_auth import create_user_in_db
from src.data_loader import load_user_data_from_firestore

# --- New Password Validation Function ---
def is_password_strong(password: str) -> str | None:
    """
    Checks all password complexity rules and returns a single, consolidated error message 
    listing ALL requirements if any rule fails, or None if validation passes.
    """
    
    # Check if ANY rule failed
    if (len(password) < 8 or
        not re.search(r'[a-z]', password) or
        not re.search(r'[A-Z]', password) or
        not re.search(r'\d', password) or
        not re.search(r'[^\w\s]', password)):
        
        # Return the single, consolidated error message
        return "Password must be at least 8 characters long, contain at least one lowercase letter and one uppercase letter, at least one digit (0-9), and contain at least one special character (e.g., !@#$%^&)."
        
    return None # Password is strong

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
                    load_user_data_from_firestore() # Fetch username and other data
                    st.rerun()
                except requests.exceptions.HTTPError as e:
                    try:
                        error_json = e.response.json()
                        # Generic login error handling is sufficient for security
                        message = "Invalid email or password." 
                    except (AttributeError, json.JSONDecodeError):
                        message = "Invalid email or password."
                    st.error(message)
            else:
                st.error("Please enter both email and password.")

    with signup_tab:
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="signup_confirm_password")
        new_username = st.text_input("Username", key="signup_username")
        signup_button = st.button("Sign Up", key="signup_button", use_container_width=True)

        if signup_button:
            if new_email and new_username and new_password and confirm_password:
                if new_password != confirm_password:
                    st.error("Passwords do not match.")
                    return
                
                # --- CLIENT-SIDE PASSWORD VALIDATION ---
                validation_error = is_password_strong(new_password)
                if validation_error:
                    st.error(validation_error)
                    return # Stop execution if password is weak
                # --- END CLIENT-SIDE PASSWORD VALIDATION ---

                try:
                    user = auth.create_user_with_email_and_password(new_email, new_password)
                    # Extract uid from the user object returned by pyrebase
                    uid = user['localId']
                    create_user_in_db(uid, new_email, new_username)
                    st.success("Account created! Please log in.")
                except requests.exceptions.HTTPError as e:
                    try:
                        error_json = e.response.json()
                        # This block now primarily handles EMAIL_EXISTS and INVALID_EMAIL errors
                        error_code = error_json.get("error", {}).get("message", "UNKNOWN_ERROR")
                        
                        if "EMAIL_EXISTS" in error_code or "INVALID_EMAIL" in error_code:
                            # Security-enhanced generic error for email issues
                            message = "Could not create account. Please ensure your email is valid and not already registered."
                        else:
                            # For other API errors, display the sanitized code
                            message = error_code.replace("_", " ").title()
                            
                    except (AttributeError, json.JSONDecodeError):
                        # Final fallback, typically for unreadable responses from an email error
                        message = "Could not create account, email already exists."
                    st.error(message)
            else:
                st.error("Please fill out all fields.")