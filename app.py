import streamlit as st
import json
import re
import os
import time
import tempfile
import ollama
from streamlit_mic_recorder import mic_recorder
from faster_whisper import WhisperModel

# Custom modules
import bq_client
from prompts import GITHUB_SCHEMA_PROMPT

st.set_page_config(page_title="GitHub SQL Agent", layout="wide")

# ---------------------------------------------------------------------------
# Tunables (single place to edit)
# ---------------------------------------------------------------------------
LLM_MODEL = "llama3"                 
LLM_OPTIONS = {
    "num_ctx": 1024,   
    "temperature": 0.0, # Keeps output deterministic and strictly logical
    "num_predict": 512,
    "num_gpu": -1,     
}
WHISPER_MODEL_NAME = "tiny.en"        
RUNNER_CRASH_HINTS = ("runner process has terminated", "llama runner", "connection refused")

st.markdown("""
<style>
.main { background-color: #ffffff; color: #111111; }
.stChatMessage {
    border: 1px solid #e5e7eb !important;
    border-radius: 8px;
    background-color: #f9fafb;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_audio_id" not in st.session_state:
    st.session_state.last_audio_id = None
if "model_warm" not in st.session_state:
    st.session_state.model_warm = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean_json_output(raw_text):
    clean_text = re.sub(r'```json\n|\n```|```', '', raw_text).strip()
    return json.loads(clean_text)

def is_runner_crash(err_msg: str) -> bool:
    msg = err_msg.lower()
    return any(h in msg for h in RUNNER_CRASH_HINTS)

# ---------------------------------------------------------------------------
# Whisper (lazy + cached, CPU fallback)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading Whisper model...")
def load_whisper_model():
    return WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")

def transcribe_audio(audio_bytes):
    try:
        model = load_whisper_model()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            segments, _ = model.transcribe(tmp_path, beam_size=1, vad_filter=False)
            text = " ".join(seg.text for seg in list(segments)).strip()
        finally:
            os.unlink(tmp_path)
        return text if text else None
    except Exception as e:
        st.error(f"Transcription failed: {e}")
        return None

# ---------------------------------------------------------------------------
# Ollama wrapper with runner-crash recovery
# ---------------------------------------------------------------------------
def check_ollama():
    try:
        ollama.list()
        return True
    except Exception:
        return False

def warm_up_model():
    if st.session_state.model_warm:
        return True
    try:
        ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "ok"}],
            options={"num_ctx": 512, "num_predict": 4},
        )
        st.session_state.model_warm = True
        return True
    except Exception as e:
        st.error(
            f"Could not load `{LLM_MODEL}`: {e}\n\n"
            f"Try in a terminal: `ollama run {LLM_MODEL} 'hi'`. "
        )
        return False

def call_llm(messages, want_json=True):
    last_err = None
    for retry in range(2):
        try:
            kwargs = dict(model=LLM_MODEL, messages=messages, options=LLM_OPTIONS)
            if want_json:
                kwargs["format"] = "json"
            output = ollama.chat(**kwargs)
            return output["message"]["content"]
        except Exception as e:
            last_err = e
            if is_runner_crash(str(e)) and retry == 0:
                time.sleep(2)
                st.session_state.model_warm = False
                continue
            raise
    raise last_err

# ---------------------------------------------------------------------------
# SQL agent
# ---------------------------------------------------------------------------
def run_self_healing_sql(user_text):
    messages = [
        {"role": "system", "content": GITHUB_SCHEMA_PROMPT},
        {"role": "user", "content": user_text},
    ]
    raw_response = ""

    for attempt in range(1, 4):
        try:
            raw_response = call_llm(messages, want_json=True)
            parsed = clean_json_output(raw_response)
            
            # Extract SQL and the critical "thinking" key
            sql = parsed["sql"]
            thinking = parsed.get("thinking", "No reasoning provided.")

            # --- Array sanitizers ---
            if "repo_name" in sql:
                m = re.search(r"repo_name\s*(?:=|LIKE)\s*'([^']+)'", sql)
                if m:
                    term = m.group(1).replace('%', '')
                    sql = re.sub(
                        r"repo_name\s*(?:=|LIKE)\s*'[^']+'",
                        f"EXISTS(SELECT 1 FROM UNNEST(repo_name) AS r_name WHERE r_name LIKE '%{term}%')",
                        sql,
                    )
            if "language LIKE" in sql:
                sql = re.sub(
                    r"language\s*LIKE\s*('[^']+')",
                    r"EXISTS(SELECT 1 FROM UNNEST(language) AS lang WHERE lang.name LIKE \1)",
                    sql,
                )
            if "language =" in sql:
                sql = re.sub(
                    r"language\s*=\s*('[^']+')",
                    r"EXISTS(SELECT 1 FROM UNNEST(language) AS lang WHERE lang.name = \1)",
                    sql,
                )

            results = bq_client.execute_bq_query(sql)
            
            # Return thinking alongside the results
            return sql, results, parsed.get("reply", ""), thinking

        except Exception as e:
            error_msg = str(e)
            st.warning(f"Attempt {attempt} failed: {error_msg}")

            if is_runner_crash(error_msg) or not raw_response:
                continue

            messages.append({"role": "assistant", "content": raw_response})
            if "too expensive" in error_msg.lower():
                feedback = "Reduce data scanned. Add LIMIT and more specific filters."
            elif "ARRAY" in error_msg or "UNNEST" in error_msg:
                feedback = "Use UNNEST() for array columns like repo_name and language."
            else:
                feedback = f"SQL error: {error_msg}. Fix the query and try again."
            messages.append({"role": "user", "content": feedback})

    return None, None, "Failed after retries.", "Failed."

def generate_natural_response(user_query, bq_results):
    if not bq_results:
        return "No matching data found in the database."
    
    top_results = bq_results[:5]
    clean_data = "\n".join([str(row) for row in top_results])
    
    # Fortify the LLM with a strict system prompt to prevent conversational hallucination
    system_prompt = "You are a strict data reporter. Do not invent data, do not hallucinate, and do not make assumptions. Report ONLY what is in the Database Results."
    
    user_prompt = (
        f"User question: {user_query}\n"
        f"Database Results:\n{clean_data}\n\n"
        f"Answer briefly. If the answer is not in the data, state that."
    )
    
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        return call_llm(messages, want_json=False).strip()
    except Exception as e:
        return f"(Could not summarise — {e})"

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("Voice-to-SQL Agent")

with st.sidebar:
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.last_audio_id = None
        st.rerun()
    st.caption("✅ Model warmed" if st.session_state.model_warm else "⚪ Model cold")

if not check_ollama():
    st.error("⚠️ Ollama is not running. Start it with `ollama serve`, then refresh.")
    st.stop()

if not st.session_state.model_warm:
    with st.spinner(f"Warming up {LLM_MODEL} (one-time, ~10–30s)..."):
        if not warm_up_model():
            st.stop()

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "sql" in msg:
            with st.expander("Agent Reasoning & SQL Data"):
                st.markdown(f"**Agent Thinking:**\n> {msg.get('thinking', 'N/A')}")
                st.code(msg["sql"], language="sql")
                st.dataframe(msg["data"])

def _process_query(text):
    with st.spinner("Generating SQL and querying BigQuery..."):
        # Unpack the 4th returned value (thinking)
        sql, results, _, thinking = run_self_healing_sql(text)
        
    if results is not None:
        with st.spinner("Summarising results..."):
            answer = generate_natural_response(text, results)
        st.session_state.messages.append({"role": "user", "content": text})
        st.session_state.messages.append({
            "role": "assistant", 
            "content": answer, 
            "sql": sql, 
            "data": results,
            "thinking": thinking # Store thinking in session state
        })
        st.rerun()
    else:
        st.error("Query failed after 3 attempts. Try rephrasing your question.")

# Text input
text_query = st.chat_input("Or type your query here...")
if text_query:
    _process_query(text_query)

# Mic input
st.divider()
st.subheader("Speak your query")

audio_data = mic_recorder(start_prompt="🎙️ Speak", stop_prompt="⏹️ Stop", key="mic")
if audio_data and audio_data.get("id") != st.session_state.last_audio_id:
    st.session_state.last_audio_id = audio_data["id"]
    with st.spinner("Transcribing..."):
        text = transcribe_audio(audio_data["bytes"])
    if text:
        st.success(f"You said: **{text}**")
        _process_query(text)
    else:
        st.warning("No speech detected. Please try again.")