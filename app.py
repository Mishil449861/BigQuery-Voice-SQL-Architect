import streamlit as st
import json
import re
import ollama
from google.api_core.exceptions import BadRequest
from streamlit_mic_recorder import mic_recorder

# Custom modules
import bq_client 
from prompts import GITHUB_SCHEMA_PROMPT

# --- PAGE CONFIG ---
st.set_page_config(page_title="GitHub SQL Agent Pro", layout="wide")

# Polished UI Styling
st.markdown("""
<style>
.main {
    background-color: #ffffff;
    color: #111111;
}

.stChatMessage {
    border: 1px solid #e5e7eb !important;
    border-radius: 8px;
    background-color: #f9fafb;
}

.st-emotion-cache-1cv06cb {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    padding: 16px;
    border-radius: 8px;
}

h1, h2, h3 {
    color: #111827;
}

</style>
""", unsafe_allow_html=True)


# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- CORE PROCESSING ---
def clean_json_output(raw_text):
    """Handles LLM markdown hallucinations."""
    clean_text = re.sub(r'```json\n|\n```|```', '', raw_text).strip()
    return json.loads(clean_text)

def run_self_healing_sql(user_text):
    messages = [
        {"role": "system", "content": GITHUB_SCHEMA_PROMPT},
        {"role": "user", "content": user_text}
    ]
    
    raw_response = "" 

    for attempt in range(1, 4):
        try:
            output = ollama.chat(model='llama3', messages=messages, format='json')
            raw_response = output['message']['content']
            parsed = clean_json_output(raw_response)
            
            sql, voice_reply = parsed['sql'], parsed['reply']
            
            # 2. Execute on BigQuery (Triggers dry-run guardrail)
            results = bq_client.execute_bq_query(sql)
            return sql, results, voice_reply
            
        except Exception as e:
            error_msg = str(e)
            st.warning(f"Attempt {attempt} Failed: {error_msg}")
            
            # 3. SELF-HEALING FEEDBACK LOOP
            messages.append({"role": "assistant", "content": raw_response})
            
            # THE SMART TRAPS
            if "too expensive" in error_msg.lower():
                feedback = f"CRITICAL ERROR: Your query scans too much data ({error_msg}). Use a more specific WHERE repo_name filter, avoid 'contents' table, and reduce LIMIT."
            
            elif "ARRAY<STRING>, STRING" in error_msg:
                # NEW: Specific trap for the stubborn array error
                feedback = f"FATAL TYPE ERROR: {error_msg}. You CANNOT use '=' or 'LIKE' on the language array! You MUST use `CROSS JOIN UNNEST(language) AS lang` and then filter using `lang.name = '...'`."
            
            else:
                feedback = f"SQL ERROR: {error_msg}. Check your JOINs and UNNEST syntax. Ensure columns like 'id' or 'commit' are used correctly."
            
            messages.append({"role": "user", "content": feedback})
            
    return None, None, "I couldn't generate a safe, valid query after 3 tries."

def generate_natural_response(user_query, bq_results):
    """Converts BigQuery JSON into a conversational voice-ready answer."""
    prompt = f"User asked: '{user_query}'\nData: {bq_results}\nAnswer naturally and briefly."
    output = ollama.chat(model='llama3', messages=[{"role": "user", "content": prompt}])
    return output['message']['content'].strip()

# --- MAIN UI ---
st.title("Voice-to-SQL Agent")
st.caption("Connected to `bigquery-public-data.github_repos` | Voice Activation Only")

# Sidebar for controls
with st.sidebar:
    st.header("Session Settings")
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "sql" in msg:
            with st.expander("View Execution Details"):
                st.code(msg["sql"], language="sql")
                st.dataframe(msg["data"])

# --- VOICE INPUT SECTION ---
st.divider()
st.write("### Ask a question using your microphone:")

# Removed the columns and text input entirely
audio_data = mic_recorder(start_prompt="Click to Speak", stop_prompt="Stop Recording", key="mic")

final_query = None

if audio_data:
    # -------------------------------------------------------------------------
    # NOTE: To make this fully functional, you need to transcribe the audio here.
    # You would pass audio_data['bytes'] to a Whisper model or API.
    # Example placeholder for transcription logic:
    # -------------------------------------------------------------------------
    final_query = "Who are the top contributors to the 'facebook/react' repo?" 

if final_query:
    with st.spinner("Analyzing voice and writing optimized SQL..."):
        sql, results, voice_ack = run_self_healing_sql(final_query)
        
        if results is not None:
            # Final conversational answer
            final_answer = generate_natural_response(final_query, results)
            
            # Store in session
            st.session_state.messages.append({"role": "user", "content": f"*Transcribed:* {final_query}"})
            st.session_state.messages.append({
                "role": "assistant", 
                "content": final_answer, 
                "sql": sql, 
                "data": results
            })
            st.rerun()
        else:
            st.error("Operation failed. Try a more specific question with a repository name.")