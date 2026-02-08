import streamlit as st
from google import genai
from google.genai import types
from gtts import gTTS
import tempfile
import os
import time
from io import BytesIO

# UI Configuration
st.set_page_config(
    page_title="Italian Chat with Gemini",
    page_icon="🇮🇹",
    layout="centered"
)

st.title("🇮🇹 Parla con Gemini")
st.markdown("Practice your Italian! Speak to Gemini and hear the response.")

# Initialize Session State
if "history" not in st.session_state:
    st.session_state.history = []
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "last_audio_id" not in st.session_state:
    st.session_state.last_audio_id = None
if "client" not in st.session_state:
    st.session_state.client = None

# API Key Configuration
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    st.error("Missing Google API Key. Please set it in `.streamlit/secrets.toml` or as an environment variable.")
    st.stop()

def text_to_audio(text):
    """Converts text to audio bytes using gTTS."""
    try:
        print("DEBUG: Generating audio via gTTS...")
        tts = gTTS(text=text, lang='it')
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        print("DEBUG: Audio generated successfully.")
        return fp
    except Exception as e:
        print(f"TTS Error: {e}")
        st.exception(e)
        return None

def init_chat():
    """Initializes the Gemini chat session."""
    if api_key and not st.session_state.client:
        try:
            client = genai.Client(api_key=api_key)
            st.session_state.client = client
            
            # Start a chat session
            chat = client.chats.create(model="gemini-2.0-flash")
            st.session_state.chat_session = chat
            
            initial_prompt = (
                "You are a friendly Italian language tutor. "
                "Greet the user in Italian and offer 3 simple topics to chat about. "
                "Keep it spoken, natural, and brief. "
                "CRITICAL: Do NOT translate to English. Check your response and ensure it is 100% Italian."
            )
            
            response = chat.send_message(initial_prompt)
            
            # Add initial greeting to history
            audio_bytes = text_to_audio(response.text)
            st.session_state.history.append({
                "role": "model",
                "text": response.text,
                "audio": audio_bytes
            })
        except Exception as e:
            st.error(f"Failed to initialize chat: {e}")

# Call init
init_chat()

# Display Chat History
chat_container = st.container()
with chat_container:
    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            if msg.get("text"):
                st.write(msg["text"])
            if msg.get("audio"):
                st.audio(msg["audio"], format="audio/mp3")

# Auto-play the latest model message if it hasn't been played yet
if st.session_state.history:
    last_msg = st.session_state.history[-1]
    if last_msg["role"] == "model" and not st.session_state.get("last_audio_played") == len(st.session_state.history):
        # This is a new message from                if last_msg.get("audio"):
                     # iOS often prefers audio/mpeg for MP3
                     st.audio(last_msg["audio"], format="audio/mpeg", autoplay=True)
                     st.session_state.last_audio_played = len(st.session_state.history)

# Audio Input Handling in Sidebar
with st.sidebar:
    st.divider()
    audio_input = st.audio_input("🎤 Record your Italian")

if audio_input is not None:
    try:
        current_audio_id = audio_input.file_id if hasattr(audio_input, 'file_id') else str(audio_input.size) # Fallback
        
        if current_audio_id != st.session_state.last_audio_id:
            st.session_state.last_audio_id = current_audio_id
            
            with st.spinner("Listening & Thinking..."):
                print(f"DEBUG: Processing audio input object: {audio_input}")
                print("DEBUG: Checking file_id/size...")
                # Read audio bytes
                audio_bytes = audio_input.getvalue()
                print(f"DEBUG: Audio bytes read: {len(audio_bytes)}")

                # Upload to Gemini
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
                    tmp_wav.write(audio_bytes)
                    tmp_wav_path = tmp_wav.name
                
                print(f"Saved temp audio to {tmp_wav_path}")

                # Upload file
                client = st.session_state.client
                if client:
                    print("Uploading file to Gemini...")
                    # Fix: use path argument if possible, or keyword 'file'
                    # The genai SDK creates a file. 
                    myfile = client.files.upload(file=tmp_wav_path)
                    print(f"File uploaded: {myfile.name}")

                    # Generate content
                    chat = st.session_state.chat_session
                    
                    # Prompt for JSON
                    prompt = (
                        "Listen to the user's Italian audio. "
                        "1. Transcribe exactly what the user said (in Italian). "
                        "2. Provide a brief analysis of grammatical errors or improvements (in English or Italian as preferred for a tutor). "
                        "3. Formulate a natural, friendly conversational response in Italian. "
                        "Output strictly VALID JSON with keys: 'transcription', 'analysis', 'response_italian'. "
                        "Do not use markdown code blocks for the JSON."
                    )
                    
                    print("Sending message to Gemini...")
                    # Send message with file
                    # Configure generation config for JSON if supported or just text
                    response = chat.send_message([prompt, myfile])
                    print("Received response from Gemini.")
                    
                    # Parse JSON
                    import json
                    # Inspect response safely
                    if not response.text:
                        print("Response text is empty. Checking candidates.")
                        # Fallback if blocked
                        raise ValueError("Gemini returned empty text (possibly safety block).")

                    text_resp = response.text.strip()
                    print(f"Raw response text: {text_resp}")

                    # Clean cleanup if model adds markdown
                    if text_resp.startswith("```json"):
                        text_resp = text_resp[7:]
                    if text_resp.endswith("```"):
                        text_resp = text_resp[:-3]
                    
                    data = json.loads(text_resp)
                    user_transcription = data.get("transcription", "")
                    analysis = data.get("analysis", "")
                    model_reply = data.get("response_italian", "")

                    # Add User Input to History
                    # Note: Don't store audio_input object as it's not serializable across reruns
                    st.session_state.history.append({
                        "role": "user",
                        "audio": None,  # Don't store the UploadedFile object
                        "text": f"**Transcription:** {user_transcription}  \n**Analysis:** {analysis}"
                    })
                    
                    # Add Model Response to History
                    resp_audio = text_to_audio(model_reply)
                    st.session_state.history.append({
                        "role": "model",
                        "text": model_reply,
                        "audio": resp_audio
                    })
                    
                    # Cleanup
                    os.unlink(tmp_wav_path)
                    
                    st.rerun()

    except Exception as e:
        st.error(f"CRITICAL ERROR: {str(e)}")
        st.write("Reference this error for debugging:")
        st.code(str(e))
        import traceback
        st.code(traceback.format_exc())
        print("EXCEPTION OCCURRED: " + str(e))
        traceback.print_exc()
