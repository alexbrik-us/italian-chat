import streamlit as st
from google import genai
from google.genai import types
from gtts import gTTS
import tempfile
import os
import time
from io import BytesIO
from io import BytesIO
try:
    from streamlit_mic_recorder import mic_recorder
except ImportError:
    st.error("Library `streamlit-mic-recorder` not found. Please run `pip install streamlit-mic-recorder`.")
    mic_recorder = None

# UI Configuration
st.set_page_config(
    page_title="Italian Chat with Gemini",
    page_icon="🇮🇹",
    layout="centered"
)

st.title("🇮🇹 Parla con Gemini")
st.markdown("Practice your Italian! Speak to Gemini and hear the response.")

print("DEBUG: Script execution started (Rerun)")

# Initialize Session State
if "history" not in st.session_state:
    st.session_state.history = []
if "chat_session" not in st.session_state:
    st.session_state.chat_session = None
if "last_audio_id" not in st.session_state:
    st.session_state.last_audio_id = None
if "client" not in st.session_state:
    st.session_state.client = None
if "audio_unlocked" not in st.session_state:
    st.session_state.audio_unlocked = False

# API Key Configuration
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = os.environ.get("GOOGLE_API_KEY")

if not api_key:
    st.error("Missing Google API Key. Please set it in `.streamlit/secrets.toml` or as an environment variable.")
    st.stop()

import base64

import streamlit.components.v1 as components

def autoplay_audio(audio_bytes):
    """Auto-plays audio on compatible browsers using HTML5."""
    b64 = base64.b64encode(audio_bytes).decode('utf-8')
    md = f"""
        <audio id="autoplayAudio" controls autoplay playsinline style="width: 100%;">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        <script>
            var audio = document.getElementById("autoplayAudio");
            if (audio) {{
                audio.play().catch(function(error) {{
                    console.log("Autoplay failed:", error);
                }});
            }}
        </script>
    """
    components.html(md, height=50)

def unlock_audio_js():
    """Inject JS to unlock audio on iOS."""
    js = """
        <script>
            // Create a silent audio context to unlock audio
            var AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                var ctx = new AudioContext();
                var buffer = ctx.createBuffer(1, 1, 22050);
                var source = ctx.createBufferSource();
                source.buffer = buffer;
                source.connect(ctx.destination);
                source.start(0);
                console.log("Audio unlocked!");
            }
        </script>
    """
    components.html(js, height=0)

def send_message_with_retry(chat, *args, retries=3, **kwargs):
    """Sends message to chat with exponential backoff on resource exhaustion."""
    for i in range(retries):
        try:
            return chat.send_message(*args, **kwargs)
        except Exception as e:
            # Check for Resource Exhausted (429) or related quota errors
            error_str = str(e).lower()
            if "429" in error_str or "resource" in error_str or "exhausted" in error_str or "quota" in error_str:
                if i < retries - 1:
                    wait_time = 2 ** (i + 1)
                    print(f"DEBUG: Resource Exhausted. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            raise e

def text_to_audio(text):
    """Converts text to audio bytes using gTTS."""
    try:
        print("DEBUG: Generating audio via gTTS...")
        tts = gTTS(text=text, lang='it')
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        print("DEBUG: Audio generated successfully.")
        return fp.getvalue() # Return raw bytes, not file-like object
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
            
            response = send_message_with_retry(chat, initial_prompt)
            
            # Add initial greeting to history
            # text_to_audio now returns bytes, which is safe for st.audio
            audio_bytes = text_to_audio(response.text)
            st.session_state.history.append({
                "role": "model",
                "text": response.text,
                "audio": audio_bytes
            })
        except Exception as e:
            st.error(f"Failed to initialize chat: {e}")



def main():
    # Call init
    init_chat()

    # Display Chat History
    chat_container = st.container()
    with chat_container:
        for i, msg in enumerate(st.session_state.history):
            with st.chat_message(msg["role"]):
                if msg.get("text"):
                    st.write(msg["text"])
                if msg.get("audio"):
                    # Determine if this audio should autoplay
                    do_autoplay = False
                    if (i == len(st.session_state.history) - 1 and 
                        msg["role"] == "model" and 
                        st.session_state.get("last_audio_played") != len(st.session_state.history)):
                        
                        do_autoplay = True
                        st.session_state.last_audio_played = len(st.session_state.history)
                    
                    if do_autoplay:
                        autoplay_audio(msg["audio"])
                    else:
                        st.audio(msg["audio"], format="audio/mpeg")

    # Audio Input Handling in Sidebar
    with st.sidebar:
        st.divider()
        try:
            if mic_recorder:
                # mic_recorder returns a dict: {'bytes': b'...', 'sample_rate': 44100, 'id': '...'}
                audio_data = mic_recorder(
                    start_prompt="Start Recording",
                    stop_prompt="Stop Recording",
                    key="recorder",
                    format="wav",
                    use_container_width=True
                )
            else:
                st.error("Mic Recorder library missing.")
                audio_data = None
            
            if audio_data and audio_data['bytes']:
                audio_bytes = audio_data['bytes']
                # Check if this is new audio
                # We can hash it or just check if it's different from last time
                audio_hash = hash(audio_bytes)
                if st.session_state.last_audio_id != audio_hash:
                    st.session_state.last_audio_id = audio_hash
                    
                    with st.spinner("Processing audio..."):
                        # Save to temp file
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
                            tmp_wav.write(audio_bytes)
                            tmp_wav_path = tmp_wav.name
                        
                        # Upload file
                        client = st.session_state.client
                        if client:
                            myfile = client.files.upload(file=tmp_wav_path)
                            
                            # Generate content
                            chat = st.session_state.chat_session
                            prompt = (
                                "Listen to the user's Italian audio. "
                                "1. Transcribe exactly what the user said (in Italian). "
                                "2. Provide a brief analysis of grammatical errors or improvements (in English or Italian as preferred for a tutor). "
                                "3. Formulate a natural, friendly conversational response in Italian. "
                                "Output strictly VALID JSON with keys: 'transcription', 'analysis', 'response_italian'. "
                                "Do not use markdown code blocks for the JSON."
                            )
                            
                            response = send_message_with_retry(chat, [prompt, myfile])
                            
                            # Parse JSON
                            import json
                            if not response.text:
                               raise ValueError("Gemini returned empty text.")

                            text_resp = response.text.strip()
                            if text_resp.startswith("```json"):
                                text_resp = text_resp[7:]
                            if text_resp.endswith("```"):
                                text_resp = text_resp[:-3]
                            
                            data = json.loads(text_resp)
                            user_transcription = data.get("transcription", "")
                            analysis = data.get("analysis", "")
                            model_reply = data.get("response_italian", "")

                            # Add User Input to History
                            st.session_state.history.append({
                                "role": "user",
                                "audio": None, 
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
                            
                            # Force rerun to show new messages
                            st.rerun()

        except Exception as e:
            st.error(f"Recorder Error: {e}")
            st.exception(e)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error("Global App Error")
        st.exception(e)
