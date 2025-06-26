import streamlit as st
from pyrebase import pyrebase
import requests
import os
import shutil
import subprocess
from urllib.parse import quote
import time
import base64
import webbrowser
import json

# Firebase configuration - Load from secure config file
try:
    with open('firebase_config.json', 'r') as f:
        firebase_config = json.load(f)
except FileNotFoundError:
    st.error("❌ Firebase configuration file not found. Please add firebase_config.json to the project root directory.")
    st.info("Create firebase_config.json with your Firebase project credentials.")
    st.stop()
except json.JSONDecodeError:
    st.error("❌ Invalid firebase_config.json format. Please check the JSON syntax.")
    st.stop()


# Page configuration
st.set_page_config(
    page_title="Archeon VR Model Viewer",
    page_icon="🕶️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Hide Streamlit default elements
st.markdown(
    """
    <style>
        /* Hide Streamlit's top-right menu and footer */
        header {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Custom app styling */
        .stApp {
            background: linear-gradient(to bottom, #000000, #1a1a2e);
            color: #ffffff;
        }
        
        /* Button styling */
        .stButton>button {
            background-color: #4a00e0;
            color: white;
            font-weight: bold;
            border: none;
            padding: 0.5rem 2rem;
            border-radius: 5px;
            transition: all 0.3s ease;
        }
        .stButton>button:hover {
            background-color: #7028e4;
            transform: translateY(-2px);
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        /* Card-like containers */
        .content-card {
            background-color: rgba(30, 30, 50, 0.7);
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        
        /* Status indicator styling */
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-online {
            background-color: #4CAF50;
        }
        .status-offline {
            background-color: #F44336;
        }
        
        /* List items styling */
        .model-item {
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 8px;
            background-color: rgba(60, 60, 80, 0.5);
            transition: all 0.2s ease;
        }
        .model-item:hover {
            background-color: rgba(80, 80, 100, 0.7);
            transform: translateX(5px);
        }
        
        /* Input fields styling */
        .stTextInput>div>div>input {
            background-color: rgba(40, 40, 60, 0.5);
            color: white;
            border: 1px solid #444;
            border-radius: 5px;
        }
        
        /* Image animation */
        @keyframes float {
            0% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
            100% { transform: translateY(0px); }
        }
        .floating-logo {
            animation: float 3s ease-in-out infinite;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize Firebase
firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()
storage = firebase.storage()

# Initialize session state for login
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user'] = None

# Helper function to get base64 image
def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as f:
            encoded_string = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{encoded_string}"
    except Exception:
        # Return a default/blank image if the logo file is not found
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

# Display logo
image_base64 = get_base64_image("logo-no-background.png")
st.markdown(
    f"""
    <div style="text-align: center;">
        <img src="{image_base64}" width="150" class="floating-logo">
    </div>
    """,
    unsafe_allow_html=True
)

# Empty space
st.text("")

# Main title with animation
st.markdown("""
    <h1 style='text-align: center; color: #ffffff; text-shadow: 0 0 10px rgba(74, 0, 224, 0.7);'>
        VR Model Viewer
    </h1>
    """, 
    unsafe_allow_html=True
)

# App description with improved styling
st.markdown("""
    <div style='text-align: center; max-width: 700px; margin: 0 auto;'>
        <p style='font-size: 16px; color: #a6a6d9; line-height: 1.6;'>
            Experience your 3D models in immersive virtual reality. Seamlessly sync your VR-ready 
            models from the cloud and visualize them in a dynamic environment.
        </p>
    </div>
    """, 
    unsafe_allow_html=True
)

# Display connection status
st.sidebar.markdown("""
    <div style='padding: 10px; border-radius: 5px; background-color: rgba(30, 30, 50, 0.7);'>
        <h4 style='margin-bottom: 10px;'>System Status</h4>
        <p>
            <span class='status-indicator status-online'></span>
            Server: Online
        </p>
        <p>
            <span class='status-indicator status-online'></span>
            Storage: Connected
        </p>
    </div>
    """, 
    unsafe_allow_html=True
)

# Updated login function with properly hidden functional button
def login():
    with st.container():
        st.markdown("""
            <div class='content-card'>
                <h2 style='text-align: center; margin-bottom: 20px; color: #8a8aff;'>
                    🔐 User Authentication
                </h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<p style='color: #a6a6d9;'>Sign in with your credentials:</p>", unsafe_allow_html=True)
            
            email = st.text_input("📧 Email Address")
            password = st.text_input("🔑 Password", type="password")
            remember_me = st.checkbox("Remember me", value=False)
            
            # Create a container to hold the login button
            login_button_container = st.container()
            
            # Add CSS to style the button
            st.markdown("""
                <style>
                    /* Custom style for the main login button */
                    div[data-testid="element-container"] button {
                        background: linear-gradient(90deg, #4a00e0, #8e2de2);
                        color: white;
                        font-weight: bold;
                        border: none;
                        padding: 10px 0;
                        border-radius: 5px;
                        transition: all 0.3s ease;
                        width: 100%;
                        cursor: pointer;
                        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
                        margin-top: 10px;
                        text-align: center;
                    }
                    div[data-testid="element-container"] button:hover {
                        background: linear-gradient(90deg, #6a20ff, #9e4dff);
                        transform: translateY(-2px);
                        box-shadow: 0 6px 10px rgba(0, 0, 0, 0.3);
                    }
                    div[data-testid="element-container"] button:active {
                        transform: translateY(1px);
                        box-shadow: 0 2px 3px rgba(0, 0, 0, 0.2);
                    }
                    
                    /* Button icon styling */
                    .button-icon {
                        display: inline-block;
                        vertical-align: middle;
                        margin-left: 10px;
                    }
                </style>
            """, unsafe_allow_html=True)
            
            # Use a single Streamlit button with the login icon added via markdown
            with login_button_container:
                login_button = st.button("Login ", 
                                        key="login_button", use_container_width=True)
            
            # Add divider
            st.markdown("""
                <div style="display: flex; align-items: center; margin: 20px 0;">
                    <div style="flex-grow: 1; height: 1px; background-color: rgba(166, 166, 217, 0.3);"></div>
                    <div style="margin: 0 10px; color: #a6a6d9; font-size: 0.8rem;">or</div>
                    <div style="flex-grow: 1; height: 1px; background-color: rgba(166, 166, 217, 0.3);"></div>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
            # Forgot password link
            st.markdown("""
                <div style='text-align: center; margin-top: 10px;'>
                    <a href='#' style='color: #a6a6d9; text-decoration: none; font-size: 0.9rem; 
                       transition: all 0.2s ease;' onmouseover="this.style.color='#ffffff';" 
                       onmouseout="this.style.color='#a6a6d9';">
                        Forgot password?
                    </a>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
            # Handle login logic when the button is clicked
            if login_button:
                with st.spinner("Authenticating..."):
                    try:
                        user = auth.sign_in_with_email_and_password(email, password)
                        st.session_state['user'] = user
                        st.session_state['logged_in'] = True
                        
                        st.success(f"🔓 Successfully logged in as {user['email']}")
                        st.snow()
                        time.sleep(3)
                        st.rerun()
                    except requests.exceptions.ConnectionError:
                        st.error("⚠ Network error. Please check your internet connection.")
                    except requests.exceptions.RequestException:
                        st.error("⚠ Server error. Please try again later.")
                    except Exception as e:
                        error_message = str(e)
                        
                        if "EMAIL_NOT_FOUND" in error_message or "INVALID_PASSWORD" in error_message:
                            st.error("⚠ Invalid email or password. Please try again.")
                        elif "TOO_MANY_ATTEMPTS_TRY_LATER" in error_message:
                            st.error("⚠ Too many failed attempts. Please try again later.")
                        elif "USER_DISABLED" in error_message:
                            st.error("⚠ This account has been disabled. Please contact support.")
                        else:
                            st.error("⚠ An unexpected error occurred. Please try again.")
# Updated render_logout_button function to properly hide the standard button
def render_logout_button():
    # Create a unique key for the logout button
    logout_key = "logout_button_hidden"
    
    # Add CSS to hide the standard button with the specific key
    st.markdown(f"""
    <style>
        /* Target the specific button by its key */
        div[data-testid="element-container"]:has(button[kind="primary"][data-testid="{logout_key}"]) {{
            display: none;
        }}
        
        .logout-btn {{
            background: linear-gradient(90deg, #434343, #656565);
            color: white;
            font-weight: 500;
            border: none;
            padding: 8px 20px;
            border-radius: 5px;
            transition: all 0.3s ease;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }}
        .logout-btn:hover {{
            background: linear-gradient(90deg, #5a5a5a, #7a7a7a);
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        }}
        .logout-btn:active {{
            transform: translateY(0px);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
        }}
    </style>
    <div class="logout-btn-container" style="display: flex; justify-content: center; margin-top: 20px; margin-bottom: 30px;">
        <button class="logout-btn" type="submit" form="logout-form">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H9" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M16 17L21 12L16 7" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M21 12H9" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span>Logout</span>
        </button>
    </div>
    <form id="logout-form"></form>
    """, unsafe_allow_html=True)
    
    # Create the hidden Streamlit button with the unique key
    return st.button("Logout", key=logout_key)

# Update the file_sync function to use the new logout button
def file_sync():
    try:
        user = st.session_state['user']
        user_id = user['localId']
        cloud_dir = f"models/{user_id}/"
        
        # Display user info in sidebar with improved UI
        st.sidebar.markdown(f"""
            <div style='padding: 15px; border-radius: 8px; background-color: rgba(30, 30, 50, 0.7); 
                 margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);'>
                <h4 style='margin-bottom: 15px; color: #8a8aff;'>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-right: 5px;">
                        <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="#8a8aff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        <path d="M12 11C14.2091 11 16 9.20914 16 7C16 4.79086 14.2091 3 12 3C9.79086 3 8 4.79086 8 7C8 9.20914 9.79086 11 12 11Z" stroke="#8a8aff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    User Profile
                </h4>
                <div style='display: flex; align-items: center; margin-bottom: 10px;'>
                    <div style='width: 40px; height: 40px; border-radius: 50%; background-color: #4a00e0; 
                         display: flex; align-items: center; justify-content: center; margin-right: 10px;'>
                        <span style='color: white; font-weight: bold;'>${user['email'].charAt(0).toUpperCase()}</span>
                    </div>
                    <div>
                        <p style='font-size: 0.9rem; margin: 0; font-weight: 500;'>
                            ${user['email']}
                        </p>
                        <p style='font-size: 0.8rem; margin: 0; color: #a6a6d9;'>
                            ID: ${user_id[:8]}...
                        </p>
                    </div>
                </div>
                <div style='height: 1px; background-color: rgba(166, 166, 217, 0.2); margin: 10px 0;'></div>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <span style='font-size: 0.8rem; color: #a6a6d9;'>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-right: 3px;">
                            <circle cx="12" cy="12" r="10" stroke="#a6a6d9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M12 6V12L16 14" stroke="#a6a6d9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                        Last login: Today
                    </span>
                    <span style='font-size: 0.8rem; padding: 2px 8px; background-color: rgba(74, 0, 224, 0.2); 
                          border-radius: 20px; color: #8a8aff;'>Active</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Main dashboard header
        st.markdown("""
            <div class='content-card'>
                <h2 style='text-align: center; color: #8a8aff;'>
                    🎮 VR Model Dashboard
                </h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # Create tabs for different sections
        tab1, tab2, tab3 = st.tabs(["📥 Model Sync", "👁️ Model Viewer", "ℹ️ Help"])
        
        with tab1:
            # Content of tab1 (same as before)
            pass
        
        with tab2:
            # Content of tab2 (same as before)
            pass
        
        with tab3:
            # Content of tab3 (same as before)
            pass
        
        # Use the enhanced logout button
        st.markdown("<br>", unsafe_allow_html=True)
        if render_logout_button():
            logout()
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        if st.button("Return to Login"):
            logout()

# Updated logout function with better transitioning
def logout():
    # Show a nice animation before logging out
    st.markdown("""
        <style>
            @keyframes fadeOut {
                from { opacity: 1; }
                to { opacity: 0; }
            }
            .logout-message {
                text-align: center;
                padding: 20px;
                border-radius: 8px;
                background-color: rgba(40, 40, 60, 0.7);
                animation: fadeOut 1s ease-in-out forwards;
                animation-delay: 0.5s;
            }
        </style>
        <div class="logout-message">
            <h3 style="color: #8a8aff;">👋 Logging out...</h3>
            <p style="color: #a6a6d9;">Thank you for using Archeon VR Model Viewer</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Clear session state
    auth.current_user = None
    st.session_state['logged_in'] = False
    st.session_state['user'] = None
    
    # Small delay for animation
    time.sleep(1)
    st.rerun()

# Ensure viewer content is in the right directory
def ensure_viewer_contents(local_dir):
    source_viewer_dir = "./viewer"
    if os.path.exists(source_viewer_dir):
        for item in os.listdir(source_viewer_dir):
            s = os.path.join(source_viewer_dir, item)
            d = os.path.join(local_dir, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

# File sync function
def file_sync():
    try:
        user = st.session_state['user']
        user_id = user['localId']
        cloud_dir = f"models/{user_id}/"
        
        # Display user info in sidebar
        st.sidebar.markdown(f"""
            <div style='padding: 15px; border-radius: 5px; background-color: rgba(30, 30, 50, 0.7); margin-bottom: 20px;'>
                <h4 style='margin-bottom: 10px;'>User Profile</h4>
                <p style='font-size: 0.9rem;'>
                    <strong>Email:</strong> {user['email']}<br>
                    <strong>ID:</strong> {user_id[:8]}...
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Main dashboard header
        st.markdown("""
            <div class='content-card'>
                <h2 style='text-align: center; color: #8a8aff;'>
                    🎮 VR Model Dashboard
                </h2>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # Create tabs for different sections
        tab1, tab2, tab3 = st.tabs(["📥 Model Sync", "👁️ Model Viewer", "ℹ️ Help"])
        
        with tab1:
            st.markdown("""
                <div style='background-color: rgba(40, 40, 60, 0.5); padding: 15px; border-radius: 8px; margin-bottom: 20px;'>
                    <h3 style='color: #8a8aff;'>🔄 Model Synchronization</h3>
                    <p style='color: #a6a6d9;'>
                        Download and synchronize your models from Firebase Storage into your local workspace 
                        for an immersive VR experience. The sync process will ensure you have the latest 
                        version of all your models.
                    </p>
                </div>
                """, 
                unsafe_allow_html=True
            )

            # Get list of files from Firebase
            base_url = f"https://firebasestorage.googleapis.com/v0/b/{firebase_config['storageBucket']}/o"
            headers = {"Authorization": f"Bearer {user['idToken']}"}
            params = {'prefix': cloud_dir}

            with st.spinner("Loading your models..."):
                response = requests.get(base_url, headers=headers, params=params)
                response.raise_for_status()

                items = response.json().get('items', [])
                user_files = [item['name'] for item in items if 'name' in item]

            # Display file list with improved styling
            st.markdown("<h4 style='color: #8a8aff;'>Available Models</h4>", unsafe_allow_html=True)
            
            if not user_files:
                st.info("📭 You don't have any models stored yet. Upload models to your Firebase storage to see them here.")
            else:
                for file in user_files:
                    file_name = os.path.basename(file)
                    file_size = "Unknown size"  # You could fetch actual size from metadata if needed
                    
                    st.markdown(f"""
                        <div class='model-item'>
                            <strong>📦 {file_name}</strong><br>
                            <small style='color: #a6a6d9;'>{file_size}</small>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
            
            # Sync button with improved styling
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Function to actually sync files
            def sync_files():
                local_dir = os.path.join("downloads", user_id)
                os.makedirs(local_dir, exist_ok=True)

                ensure_viewer_contents(local_dir)  # Ensure viewer contents are in the user's directory

                if not user_files:
                    st.info("No files to sync.")
                    return

                # Progress tracking
                progress_container = st.container()
                overall_progress = st.progress(0)
                file_progress = st.empty()
                
                for i, cloud_path in enumerate(user_files):
                    file_name = os.path.basename(cloud_path)
                    local_path = os.path.join(local_dir, file_name)
                    
                    # Update progress text
                    file_progress.markdown(f"Processing **{file_name}** ({i+1}/{len(user_files)})")
                    
                    # Download only if not present locally
                    if not os.path.exists(local_path):
                        with progress_container:
                            st.markdown(f"⬇️ Downloading: **{file_name}**")
                            
                        encoded_path = quote(cloud_path, safe='')
                        file_download_url = f"{base_url}/{encoded_path}?alt=media"
                        file_response = requests.get(file_download_url, headers=headers)
                        
                        if file_response.status_code == 200:
                            with open(local_path, 'wb') as f:
                                f.write(file_response.content)
                            with progress_container:
                                st.success(f"✔️ Downloaded {file_name}")
                        else:
                            with progress_container:
                                st.error(f"❌ Failed to download {file_name}")
                    else:
                        with progress_container:
                            st.info(f"ℹ️ {file_name} already present, skipping...")
                    
                    # Update overall progress
                    overall_progress.progress((i + 1) / len(user_files))
                
                # Show completion message with animation
                st.success("🎉 All files synced successfully!")
                st.balloons()

            if st.button("Sync Models", key="sync_button"):
                sync_files()

        with tab2:
            st.markdown("""
                <div style='background-color: rgba(40, 40, 60, 0.5); padding: 15px; border-radius: 8px; margin-bottom: 20px;'>
                    <h3 style='color: #8a8aff;'>🕶️ Model Visualization</h3>
                    <p style='color: #a6a6d9;'>
                        Launch the VR Model Viewer application to experience your models in an immersive 
                        virtual reality environment. The viewer provides interactive controls for 
                        rotating, scaling, and exploring your models.
                    </p>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
            # System requirements info
            with st.expander("📋 System Requirements", expanded=False):
                st.markdown("""
                    - **Operating System:** Windows 10/11 64-bit
                    - **Processor:** Intel i5/AMD Ryzen 5 or better
                    - **Memory:** 8GB RAM minimum (16GB recommended)
                    - **Graphics:** NVIDIA GTX 1060 / AMD RX 580 or better
                    - **Storage:** 500MB available space + space for models
                    - **VR Hardware:** Compatible with Oculus Rift/Quest, HTC Vive, Valve Index
                """)
            
            # View Models button
            if st.button("Launch Viewer", key="viewer_button"):
                try:
                    local_dir = os.path.join("downloads", user_id)
                    exe_path = os.path.join(local_dir, "ArcheonViewer.exe")
                    
                    # Check if file exists
                    if os.path.exists(exe_path):
                        with st.spinner("Starting the Model Viewer..."):
                            subprocess.Popen(exe_path, cwd=local_dir)
                            time.sleep(2)  # Give time for the application to start
                        st.success("🎨 VR Model Viewer launched successfully!")
                    else:
                        st.error("Viewer executable not found. Please sync your files first.")
                except Exception as e:
                    st.error(f"Failed to launch viewer: {str(e)}")
            if st.button("Launch embedded Non-VR Viewer", key="web_viewer_button"):
                st.components.v1.html(
                    f'<iframe src="http://127.0.0.1:8080/index.html" width="800" height="600"></iframe>',
                    height=600,
                    width=1000
                )
            # Button to open viewer in a new tab
            if st.button("Launch Non-VR Viewer", key="new_tab_button"):
                url = "http://127.0.0.1:8080/index.html"
                chrome_path = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s'  # Ensure correct path format

                # Open URL in Google Chrome
                webbrowser.get(chrome_path).open(url)

        
        with tab3:
            st.markdown("### ℹ️ Help & Support", unsafe_allow_html=True)
            st.markdown("Find answers to common questions and learn how to create, upload, and view your immersive 3D environments using Gaussian Splats technology.")
            
            # Main workflow explanation with Streamlit components instead of raw HTML
            st.subheader("How It Works")
            
            # Create 4-column workflow
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown("### 📱")
                st.markdown("**Capture video**")
            
            with col2:
                st.markdown("### ⚙️")
                st.markdown("**Convert to 3D**")
            
            with col3:
                st.markdown("### 🔄")
                st.markdown("**Sync models**")
            
            with col4:
                st.markdown("### 🕶️")
                st.markdown("**Experience in VR**")
            
            # Detailed workflow accordions
            with st.expander("🎥 Recording Environments with the Mobile App", expanded=True):
                st.markdown("""
                The first step is capturing your environment using our mobile app:
                
                1. **Download the Archeon Mobile App** from the App Store or Google Play
                2. **Log in** with the same account you use for this desktop application
                3. **Record a video** of the environment you want to convert to 3D
                - Walk around the space to capture it from multiple angles
                - Move slowly for better quality results
                - Ensure good lighting conditions
                - Try to cover all areas of interest
                4. **Upload the video** directly from the mobile app
                5. **Wait for processing** - you'll receive a notification when your 3D model is ready
                
                The app uses advanced computer vision to track the camera's position as you move through the space.
                """)
                    
            with st.expander("🧪 Gaussian Splat Technology", expanded=False):
                tech_col1, tech_col2 = st.columns([2, 1])
                
                with tech_col1:
                    st.markdown("""
                    Your videos are converted to 3D models using Gaussian Splats:
                    
                    - **Advanced AI processing** extracts 3D information from your 2D video
                    - **Gaussian Splats** represent the environment as a cloud of 3D points with color and depth
                    - **Advantages over traditional 3D meshes:**
                    - Photorealistic representation of real environments
                    - Faster loading and rendering times
                    - Lower file sizes for complex scenes
                    - Better visual quality for captured real-world spaces
                    
                    Our cloud servers handle all the complex processing automatically - you just provide the video!
                    """)
                
                with tech_col2:
                    st.markdown("#### Format Details")
                    st.markdown("**File extension:** .gs")
                    st.markdown("**Average size:** 5-50MB")
                    st.markdown("**Processing time:** 15-30 mins")
                    st.markdown("**Supported by:** Archeon Viewer")
            
            with st.expander("🔄 Syncing & Viewing Your 3D Models", expanded=False):
                st.markdown("""
                Once your environment has been processed:
                
                1. **Open this desktop application** and log in with your account
                2. **Navigate to the "Model Sync" tab** to see all your processed environments
                3. **Click "Sync Models"** to download your 3D environments to your local computer
                4. **Go to the "Model Viewer" tab** and click "Launch Viewer"
                5. **Experience your captured environments in VR** with full 6DOF movement
                
                Your models are automatically stored in the cloud, so you can access them from any device by logging into your account.
                """)
            
            # Tips & Troubleshooting
            with st.expander("💡 Tips for Best Results", expanded=False):
                st.markdown("#### For optimal quality 3D environments:")
                
                st.markdown("**Recording tips:**")
                st.markdown("""
                - Ensure good, even lighting (avoid harsh shadows or extremely bright areas)
                - Move slowly and steadily when recording
                - Capture the space from multiple angles and positions
                - Record for at least 60 seconds to gather sufficient data
                - Avoid highly reflective surfaces when possible
                """)
                
                st.markdown("**VR viewing tips:**")
                st.markdown("""
                - Make sure your VR headset is properly calibrated
                - Set up your play area with sufficient space to move
                - Use the in-viewer controls to adjust scale if needed
                - Try different lighting modes for different atmospheres
                """)
            
            # Troubleshooting section
            with st.expander("🛠️ Troubleshooting", expanded=False):
                st.markdown("#### Common Issues:")
                
                st.markdown("**Model appears distorted or incomplete:**")
                st.markdown("""
                - The recording may not have captured enough angles of the environment
                - Try recording again with more movement around the space
                - Ensure adequate lighting during recording
                """)
                
                st.markdown("**Sync process fails:**")
                st.markdown("""
                - Check your internet connection
                - Verify you have enough disk space on your computer
                - Try logging out and logging back in
                """)
                
                st.markdown("**Viewer doesn't launch:**")
                st.markdown("""
                - Ensure your computer meets the minimum requirements
                - Check that all files have been synced properly
                - Try restarting the application
                - Make sure your VR headset is connected and set up correctly
                """)
            
            # Contact support section
            st.subheader("Need More Help?")
            st.markdown("Our support team is ready to assist you with any questions or issues.")
            
            support_col1, support_col2, support_col3 = st.columns(3)
            
            with support_col1:
                st.markdown("**📧 Email**")
                st.markdown("support@archeon.ai")
            
            with support_col2:
                st.markdown("**💬 Discord**")
                st.markdown("discord.gg/archeon")
            
            with support_col3:
                st.markdown("**📚 Documentation**")
                st.markdown("docs.archeon.ai")   
        
             # Logout button at the bottom
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", key="logout_button"):
            logout()
        
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        if st.button("Return to Login"):
            logout()

# Main app flow
if st.session_state['logged_in']:
    file_sync()
else:
    login()