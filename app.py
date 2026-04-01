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
    .main { background-color: #0d1117; }
    .stChatMessage { border: 1px solid #30363d !important; border-radius: 12px; }
    .st-emotion-cache-1cv06cb { background: #161b22; border: 1px dashed #30363d; padding: 20px; border-radius: 10px; }
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
    """Retries with error feedback to fix cost and syntax issues."""
    messages = [
        {"role": "system", "content": GITHUB_SCHEMA_PROMPT},
        {"role": "user", "content": user_text}
    ]
    
    for attempt in range(1, 4):
        try:
            # 1. Generate SQL
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
            
            if "too expensive" in error_msg.lower():
                # Specific instructions to reduce scan size
                feedback = f"CRITICAL ERROR: Your query scans too much data ({error_msg}). Use a more specific WHERE repo_name filter, avoid 'contents' table, and reduce LIMIT."
            else:
                # Syntax or schema error feedback
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
st.caption("Connected to `bigquery-public-data.github_repos`")

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

# Input Section
st.divider()
input_col, mic_col = st.columns([5, 1])

with mic_col:
    audio_data = mic_recorder(start_prompt="🎙️", stop_prompt="🛑", key="mic")

with input_col:
    user_text = st.chat_input("Ask about a repository...")

# Logic Trigger
final_query = user_text
if audio_data:
    # Example placeholder for transcription logic
    final_query = "Who are the top contributors to the 'facebook/react' repo?" 

if final_query:
    with st.spinner("Writing optimized SQL..."):
        sql, results, voice_ack = run_self_healing_sql(final_query)
        
        if results is not None:
            # Final conversational answer
            final_answer = generate_natural_response(final_query, results)
            
            # Store in session
            st.session_state.messages.append({"role": "user", "content": final_query})
            st.session_state.messages.append({
                "role": "assistant", 
                "content": final_answer, 
                "sql": sql, 
                "data": results
            })
            st.rerun()
        else:
            st.error("Operation failed. Try a more specific question with a repository name.")