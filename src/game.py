import streamlit as st
from src.session import append_msg
import re

def has_uppercase(password: str) -> bool:
    """Check if the password has an uppercase letter."""
    return any(c.isupper() for c in password)

def has_number(password: str) -> bool:
    """Check if the password has a number."""
    return any(c.isdigit() for c in password)

def has_symbol(password: str) -> bool:
    """Check if the password has a symbol."""
    return bool(re.search(r"[!@#$%^&*(),.?:{}|<>]", password))

def handle_password_game(user_msg: str, is_recursive: bool = False):
    """Handles the password game logic with corrected recursion."""
    
    # Only append the user's message if this is the FIRST time processing it
    if not is_recursive:
        append_msg("user", user_msg)
        
    step = st.session_state.get("password_game_step", 0)
    
    # Helper to clearly show what the bot is checking
    echo_text = (
        f"You entered: `{user_msg}`.\n"
        "*(⚠️ **Safety Reminder**: This is a simulation using a fake practice password. "
        "Never enter your real passwords here.)*\n\n"
    )

    if step == 0:
        append_msg("assistant", "Great! Let's start. Please enter a simple passphrase to begin.")
        st.session_state.password_game_step = 1
        
    elif step == 1:
        st.session_state.user_password = user_msg
        if not has_uppercase(user_msg):
            append_msg("assistant", f"{echo_text} Good start! Now, try adding at least one **uppercase letter** to make it stronger.")
            st.session_state.password_game_step = 2
        else:
            append_msg("assistant", f"{echo_text} Excellent! Your password already has an uppercase letter. Let's move to the next step.")
            st.session_state.password_game_step = 3
            # If they already have a number too, we can skip ahead
            if has_number(user_msg):
                handle_password_game(user_msg, is_recursive=True) 

    elif step == 2:
        # Goal: Add Uppercase
        st.session_state.user_password = user_msg
        if has_uppercase(user_msg):
            append_msg("assistant", f"{echo_text} Great job! The uppercase letter makes your password much harder to guess. Now, let's add a **number**.")
            st.session_state.password_game_step = 3
            
            # --- FIX: Only recurse if they ALREADY have a number ---
            if has_number(user_msg):
                handle_password_game(user_msg, is_recursive=True) 
        else:
            append_msg("assistant", f"{echo_text} Not quite. Remember to add at least one **uppercase letter**. Give it another try!")

    elif step == 3:
        # Goal: Add Number (Must KEEP Uppercase)
        st.session_state.user_password = user_msg
        
        # 1. Check Regression: Did they lose the Uppercase letter?
        if not has_uppercase(user_msg):
            append_msg("assistant", f"{echo_text} Oops! You added a number, but it looks like you lost the **uppercase letter**. Please make sure your password has BOTH an uppercase letter and a number.")
            # We stay at Step 3 so they can fix it
            
        # 2. Check Progress: Did they add a number?
        elif has_number(user_msg):
            append_msg("assistant", f"{echo_text} Awesome! Numbers add another layer of complexity. Finally, let's add a **special symbol** like !, @, #, etc.")
            st.session_state.password_game_step = 4
            
            # --- FIX: Only recurse if they ALREADY have a symbol ---
            if has_symbol(user_msg):
                handle_password_game(user_msg, is_recursive=True)
        else:
            append_msg("assistant", f"{echo_text} Almost there! You still have the uppercase letter, but don't forget to add a **number**.")

    elif step == 4:
        # Goal: Add Symbol (Must KEEP Uppercase and Number)
        st.session_state.user_password = user_msg
        
        # 1. Check Regressions
        missing_requirements = []
        if not has_uppercase(user_msg):
            missing_requirements.append("uppercase letter")
        if not has_number(user_msg):
            missing_requirements.append("number")
            
        if missing_requirements:
            missing_str = " and ".join(missing_requirements)
            append_msg("assistant", f"{echo_text} You're adding a symbol, but it looks like you removed the **{missing_str}**! A strong password needs all three elements together.")
        
        # 2. Check Victory
        elif has_symbol(user_msg):
            success_msg = (
                f"🎉 **Congratulations!** You've created a strong password: `{user_msg}`.\n\n"
                "It has:\n"
                "✅ Uppercase letters\n"
                "✅ Numbers\n"
                "✅ Special symbols\n\n"
                "*(⚠️ **Final Note**: Because you typed this password into a chat interface, you should consider it 'burned'. "
                "Do not use this exact password for your real accounts. Use the structure you learned here to create a new one!)*\n\n"
                "**Great job! The game is now over. You can continue asking questions about cybersecurity now.**"
            )
            append_msg("assistant", success_msg)
            st.session_state.in_password_game = False
            st.session_state.password_game_step = 0
            st.session_state.password_question_count = 0
        else:
            append_msg("assistant", f"{echo_text} You're so close! You have the uppercase letter and number... just add a **special symbol** (e.g., !, @, #, $) to finish!")

    if not is_recursive:
        st.rerun()