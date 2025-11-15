import streamlit as st
import pyrebase

@st.cache_resource
def initialize_firebase():
    """
    Initializes the Pyrebase app using credentials from st.secrets.
    Returns the pyrebase app object, caching it for efficiency.
    """
    if "firebase" not in st.secrets:
        st.error("Firebase configuration not found. Please add it to your .streamlit/secrets.toml file.")
        return None

    try:
        firebase_config = {
            "apiKey": st.secrets.firebase.apiKey,
            "authDomain": st.secrets.firebase.authDomain,
            "projectId": st.secrets.firebase.projectId,
            "storageBucket": st.secrets.firebase.storageBucket,
            "messagingSenderId": st.secrets.firebase.messagingSenderId,
            "appId": st.secrets.firebase.appId,
            "databaseURL": ""  # Not needed for auth, but pyrebase requires it.
        }
        app = pyrebase.initialize_app(firebase_config)
        return app
    except Exception as e:
        st.error(f"Failed to initialize Firebase: {e}")
        return None

def get_auth():
    """
    Helper function to get the auth object from the initialized app.
    """
    app = initialize_firebase()
    return app.auth() if app else None
