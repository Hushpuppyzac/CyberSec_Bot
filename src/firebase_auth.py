import streamlit as st
import pyrebase
import firebase_admin
from firebase_admin import credentials, firestore
import json
from typing import Dict, Any, List, Tuple
import base64
from cryptography.fernet import Fernet

# --- Pyrebase (for Firebase Authentication) ---
@st.cache_resource
def initialize_pyrebase():
    """
    Initializes Pyrebase for client-side authentication, using [firebase] secrets.
    """
    if "firebase" not in st.secrets:
        st.error("Firebase Auth configuration not found in secrets.toml under [firebase].")
        return None
    
    try:
        firebase_config = {
            "apiKey": st.secrets.firebase.apiKey,
            "authDomain": st.secrets.firebase.authDomain,
            "projectId": st.secrets.firebase.projectId,
            "storageBucket": st.secrets.firebase.storageBucket,
            "messagingSenderId": st.secrets.firebase.messagingSenderId,
            "appId": st.secrets.firebase.appId,
            "databaseURL": st.secrets.firebase.get("databaseURL", "") 
        }
        app = pyrebase.initialize_app(firebase_config)
        return app
    except Exception as e:
        st.error(f"Failed to initialize Pyrebase: {e}")
        return None

def get_auth():
    """
    Returns the auth object for Firebase Authentication.
    """
    app = initialize_pyrebase()
    return app.auth() if app else None

# --- Firebase Admin SDK (for Firestore Database) ---
@st.cache_resource
def initialize_firebase_admin():
    """
    Initializes Firebase Admin SDK for Firestore access, using a Base64 encoded JSON secret.
    """
    if not firebase_admin._apps:
        if "firebase_service_account_base64" not in st.secrets:
            st.error("Firebase Admin SDK configuration not found. Missing 'firebase_service_account_base64' section in secrets.toml.")
            return None
        
        try:
            # Access the nested key to get the string value
            base64_string = st.secrets.firebase_service_account_base64.firebase_service_account_base64
            
            # Decode the base64 string into bytes and load as a dictionary
            json_bytes = base64.b64decode(base64_string)
            cred_dict = json.loads(json_bytes.decode('utf-8'))

            # Initialize the app using the dictionary
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            
        except Exception as e:
            if "already exists" not in str(e):
                st.error(f"Failed to initialize Firebase Admin SDK. Please verify base64 key. Error: {e}")
                return None
    
    return firebase_admin.get_app()

@st.cache_resource
def get_firestore_db():
    """
    Returns Firestore database client.
    """
    app = initialize_firebase_admin()
    if app:
        return firestore.client(app)
    return None

@st.cache_resource
def get_encryption_cipher():
    """
    Initializes and returns a Fernet cipher using the key from st.secrets.
    """
    if "encryption" not in st.secrets or "chat_encryption_key" not in st.secrets.encryption:
        st.error("Encryption key not found in secrets.toml under [encryption]. Please add 'chat_encryption_key'.")
        return None
    try:
        key = st.secrets.encryption.chat_encryption_key.encode()
        return Fernet(key)
    except Exception as e:
        st.error(f"Failed to initialize encryption cipher: {e}")
        return None

# --- Firestore User and Conversation Helper Functions ---

def create_user_in_db(uid: str, email: str, username: str):
    """
    Creates a new user document in Firestore on sign-up.
    """
    db = get_firestore_db()
    if db:
        try:
            user_ref = db.collection("users").document(uid)
            user_ref.set({
                "email": email,
                "username": username,
                "created_at": firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            st.error(f"Failed to create user in Firestore: {e}")

def get_user_data(uid: str) -> Dict[str, Any] | None:
    """
    Retrieves user's profile data (e.g., username) from Firestore.
    """
    db = get_firestore_db()
    if db:
        try:
            user_ref = db.collection("users").document(uid)
            user_doc = user_ref.get()
            if user_doc.exists:
                return user_doc.to_dict()
        except Exception as e:
            st.error(f"Failed to retrieve user from Firestore: {e}")
    return None

def load_conversations_from_firestore(uid: str) -> Dict[str, Any]:
    """
    Loads all conversation documents from the user's 'conversations' subcollection,
    decrypts them, and sorts them by creation time (Oldest First).
    """
    db = get_firestore_db()
    cipher = get_encryption_cipher()
    if not db or not cipher:
        return {}

    # We use a list to store data temporarily so we can sort it
    loaded_chats = [] 

    try:
        col_ref = db.collection("users").document(uid).collection("conversations")
        docs = col_ref.stream()
        
        for doc in docs:
            chat_id = doc.id
            data = doc.to_dict()
            
            if 'encrypted_data' in data:
                try:
                    # Decrypt and parse JSON
                    encrypted_data = data['encrypted_data']
                    decrypted_bytes = cipher.decrypt(encrypted_data)
                    decrypted_string = decrypted_bytes.decode()
                    clean_session = json.loads(decrypted_string)
                    
                    # Convert history from list of dictionaries back to list of tuples
                    if 'history' in clean_session and isinstance(clean_session['history'], list):
                        clean_session['history'] = [
                            (msg['role'], msg['content']) for msg in clean_session['history']
                        ]
                    
                    # Append tuple: (creation_time, chat_id, session_data)
                    loaded_chats.append((doc.create_time, chat_id, clean_session))
                
                except Exception as e:
                    print(f"Skipping corrupt chat {chat_id}: {e}")
                    continue
        
        # --- CHANGED: Removed 'reverse=True' to default to Ascending order (Oldest First) ---
        loaded_chats.sort(key=lambda x: x[0]) 

        # Reconstruct the dictionary in the sorted order
        convos = {chat_id: session for (_, chat_id, session) in loaded_chats}
            
        return convos
    except Exception as e:
        st.error(f"Failed to load conversations: {e}")
        return {}

def save_conversations_to_firestore(uid: str, convos: Dict[str, Any]):
    """
    Saves each conversation in the 'convos' dictionary as a separate document
    in the 'conversations' subcollection in Firestore, with encryption.
    Only saves conversations that have a history.
    """
    db = get_firestore_db()
    cipher = get_encryption_cipher()
    if not db or not cipher:
        return
        
    try:
        for conv_id, session_data in convos.items():
            # Only save if the conversation has history
            if session_data.get("history"):
                doc_ref = db.collection("users").document(uid).collection("conversations").document(conv_id)
                
                # Prepare data for saving
                clean_session = dict(session_data)
                if 'history' in clean_session and isinstance(clean_session['history'], list):
                    # Convert list of (role, msg) tuples to a list of dictionaries
                    clean_session['history'] = [
                        {'role': role, 'content': msg} for role, msg in clean_session['history']
                    ]
                
                # Convert to JSON string and encrypt
                json_string = json.dumps(clean_session)
                encrypted_data = cipher.encrypt(json_string.encode())
                
                # Save encrypted data (as bytes) to Firestore
                doc_ref.set({'encrypted_data': encrypted_data}, merge=True)
            else:
                # If a chat becomes empty, delete it from Firestore
                doc_ref = db.collection("users").document(uid).collection("conversations").document(conv_id)
                doc_ref.delete()
                
    except Exception as e:
        st.error(f"Failed to save conversations: {e}")

def delete_conversation_from_firestore(uid: str, chat_id: str):
    """
    Deletes a specific conversation document from the user's 'conversations' subcollection in Firestore.
    """
    db = get_firestore_db()
    if not db:
        return
    
    try:
        doc_ref = db.collection("users").document(uid).collection("conversations").document(chat_id)
        doc_ref.delete()
    except Exception as e:
        st.error(f"Failed to delete conversation: {e}")
