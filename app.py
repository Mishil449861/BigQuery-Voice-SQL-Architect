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

st.set_page_config(page_title="GitHub SQL Agent Pro", layout="wide")

# ---------------------------------------------------------------------------
# Tunables (single place to edit)
# ---------------------------------------------------------------------------
LLM_MODEL = "llama3"                 
LLM_OPTIONS = {
    "num_ctx": 1024,   # Lowered from 2048 to save ~500MB of VRAM
    "temperature": 0.1,
    "num_predict": 512,
    "num_gpu": -1,     # The magic number: -1 strictly forces ALL model layers onto the GPU
}
WHISPER_MODEL_NAME = "tiny.en"        # was "base" — 5x faster on CPU, 75MB vs 140MB
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
    # Bypasses CUDA entirely, no DLLs required
    return WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")

def transcribe_audio(audio_bytes):
    try:
        model = load_whisper_model()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            # vad_filter=False avoids a one-time silero-vad download that can
            # appear to "hang forever" on first run with no progress indicator
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
    """
    Pre-load llama3 into Ollama's memory ONCE at app startup, BEFORE Whisper
    is loaded. Ollama keeps the model resident for 5 min by default, so it
    will still be hot when the user submits a query. This is the key fix for
    the 'runner process terminated' OOM crash — we avoid loading both
    llama3 and Whisper at the same moment.
    """
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
            f"If that hangs or crashes, check `%LOCALAPPDATA%\\Ollama\\logs\\server.log`."
        )
        return False

def call_llm(messages, want_json=True):
    """
    Single LLM call with one auto-retry specifically for runner crashes.
    Distinguishes crashes (retry as-is) from real errors (raise to caller).
    """
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
                # Give Ollama 2s to clean up the dead runner, then try once more
                time.sleep(2)
                st.session_state.model_warm = False
                continue
            raise
    raise last_err

# ---------------------------------------------------------------------------
# SQL agent — self-healing only on real SQL errors, not on runner crashes
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
            sql = parsed["sql"]

            # --- Array sanitizers (safety net for the LLM) ---
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
            return sql, results, parsed.get("reply", "")

        except Exception as e:
            error_msg = str(e)
            st.warning(f"Attempt {attempt} failed: {error_msg}")

            # If the model itself crashed, there is no assistant turn worth
            # feeding back. Just retry the same prompt cleanly.
            if is_runner_crash(error_msg) or not raw_response:
                continue

            # Real SQL/parse error — feed it back for self-healing
            messages.append({"role": "assistant", "content": raw_response})
            if "too expensive" in error_msg.lower():
                feedback = "Reduce data scanned. Add LIMIT and more specific filters."
            elif "ARRAY" in error_msg or "UNNEST" in error_msg:
                feedback = "Use UNNEST() for array columns like repo_name and language."
            else:
                feedback = f"SQL error: {error_msg}. Fix the query and try again."
            messages.append({"role": "user", "content": feedback})

    return None, None, "Failed after retries."

def generate_natural_response(user_query, bq_results):
    if not bq_results:
        return "No matching data found."
    
    # 1. Slice only the top 5 results so we don't overwhelm the LLM's context window
    top_results = bq_results[:5]
    
    # 2. Convert the messy JSON into a clean, readable string
    clean_data = "\n".join([str(row) for row in top_results])
    
    # 3. Add a strict constraint to the prompt
    prompt = (
        f"User question: {user_query}\n"
        f"Database Results:\n{clean_data}\n\n"
        f"Answer the user's question briefly and naturally. "
        f"CRITICAL: You must ONLY use the numbers and names provided in the Database Results above. Do not invent or guess any information."
    )
    
    try:
        return call_llm([{"role": "user", "content": prompt}], want_json=False).strip()
    except Exception as e:
        return f"(Could not summarise — {e})"

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("Voice-to-SQL Agent")
st.caption("Whisper-powered + BigQuery + Self-healing SQL")

with st.sidebar:
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.last_audio_id = None
        st.rerun()
    st.caption(f"LLM: `{LLM_MODEL}`")
    st.caption(f"Whisper: `{WHISPER_MODEL_NAME}`")
    st.caption("✅ Model warmed" if st.session_state.model_warm else "⚪ Model cold")

if not check_ollama():
    st.error("⚠️ Ollama is not running. Start it with `ollama serve`, then refresh.")
    st.stop()

# Pre-warm BEFORE Whisper to keep peak memory low
if not st.session_state.model_warm:
    with st.spinner(f"Warming up {LLM_MODEL} (one-time, ~10–30s)..."):
        if not warm_up_model():
            st.stop()

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "sql" in msg:
            with st.expander("SQL + Data"):
                st.code(msg["sql"], language="sql")
                st.dataframe(msg["data"])

def _process_query(text):
    with st.spinner("Generating SQL and querying BigQuery..."):
        sql, results, _ = run_self_healing_sql(text)
    if results is not None:
        with st.spinner("Summarising results..."):
            answer = generate_natural_response(text, results)
        st.session_state.messages.append({"role": "user", "content": text})
        st.session_state.messages.append({
            "role": "assistant", "content": answer, "sql": sql, "data": results,
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