# 🎙️ Voice-to-SQL Agent

An end-to-end, locally hosted voice assistant that transcribes spoken language into database queries, executes them securely on Google BigQuery, and translates the raw data back into natural, conversational answers.

## ✨ Features

* **Real-time Voice Transcription:** Uses `faster-whisper` (`tiny.en`) to quickly and accurately capture audio input.
* **Local AI Processing:** Leverages Ollama running locally (optimized for models like `qwen2.5-coder` and `deepseek-coder`) to map natural language to structured SQL syntax without relying on expensive LLM APIs.
* **Self-Healing SQL Pipeline:** If BigQuery throws a syntax or execution error, the agent intercepts the error, feeds it back to the LLM, and automatically corrects the query (e.g., automatically applying `UNNEST()` for array columns).
* **Cost Safety Guardrails:** Implements a dry-run check before execution, automatically rejecting queries that scan more than 150 GB of data to protect BigQuery free-tier limits.
* **Natural Language Summarization:** Feeds the structured JSON results back through the LLM to generate a clean, human-readable summary.

## 🛠️ Tech Stack

* **Frontend:** Streamlit + `streamlit_mic_recorder`
* **Audio Processing:** `faster-whisper`
* **LLM Engine:** Ollama
* **Database:** Google Cloud BigQuery (`google-cloud-bigquery`)

## 🚀 Setup & Installation

### 1. Prerequisites
* Python 3.10+
* **Ollama** installed on your machine.
* A Google Cloud Service Account JSON key with BigQuery access.

### 2. Environment Setup
Clone the repository and install the required dependencies:

python -m venv .venv
.\.venv\Scripts\activate  # Windows
pip install -r requirements.txt

### 3. Model Preparation
Pull a highly capable, efficient coding model using Ollama:

ollama pull qwen2.5-coder:7b
*or*
ollama pull deepseek-coder:6.7b

*(Ensure `LLM_MODEL` in `app.py` matches the model you pulled).*

### 4. BigQuery Credentials
Update `bq_client.py` with the absolute path to your Google Cloud Service Account `.json` key file:

KEY_PATH = r"C:/path/to/your/service-account.json"


## 🧠 Managing VRAM & GPU Memory

Running both Whisper and a local LLM simultaneously requires careful VRAM management, especially on GPUs with 8GB or less. 

If you encounter `%!w(<nil>)` runner crashes or out-of-memory errors, you can adjust `app.py` to balance the load:
* **Offload Whisper to CPU:** Change the `device` parameter in `load_whisper_model()` from `"cuda"` to `"cpu"`.
* **Cap LLM VRAM Usage:** Adjust `num_ctx` (e.g., 1024) and `num_gpu` in `LLM_OPTIONS` to prevent the model from monopolizing the GPU.
* **Resolve Windows DLL Issues:** If PyTorch fails to load CUDA for Whisper, you may need to copy `cublas64_12.dll` from your virtual environment's `torch/lib` folder to the root project directory.

## 🏃 Usage

Start the Streamlit interface:

streamlit run app.py

1. Wait for the models to load into memory.
2. Click the mic button and speak a query (e.g., *"What are the top 5 repos by commit count?"*).
3. Review the generated SQL, raw data, and conversational summary on the screen!