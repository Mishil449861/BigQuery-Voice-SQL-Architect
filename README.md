# Voice-to-SQL Agent

A local AI agent that translates natural language voice commands into BigQuery SQL queries, executes them against the public GitHub dataset, and summarizes the results. The system features a self-healing SQL execution loop that automatically catches and corrects syntax or schema errors.

## Features

* Voice Interface: Speak natural language queries using local speech-to-text.
* Self-Healing SQL: Automatically catches BigQuery errors and reprompts the LLM to fix its own syntax.
* Dual Interfaces: Includes a Streamlit web UI and a rich CLI terminal interface.
* Cost Guardrails: Built-in 150 GB scan limit per query to prevent runaway BigQuery costs.
* Local AI: Uses Ollama (Llama 3) for SQL generation and Faster-Whisper for transcription to keep compute local.

## Tech Stack

* Frontend: Streamlit (Web), Rich (CLI)
* AI Engine: Ollama (Llama 3)
* Audio Processing: Faster-Whisper, RealtimeSTT, RealtimeTTS
* Database: Google BigQuery (Google Cloud Platform)

## Prerequisites

1. Python 3.8+
2. Google Cloud Account with BigQuery API enabled.
3. A GCP Service Account JSON key.
4. Ollama installed and running locally.

## Installation

1. Install the required Python packages:
   pip install -r requirements.txt

2. Download the Llama 3 model via Ollama:
   ollama pull llama3

3. Configure your BigQuery credentials:
   Open `bq_client.py` and update the `KEY_PATH` variable to point to your GCP Service Account JSON key file.

## Usage

Start the local Ollama server before running the applications:
ollama serve

Option A: Streamlit Web UI
Run the web application with interactive chat and data visualization:
streamlit run app.py

Option B: Terminal CLI Interface
Run the terminal application with real-time text-to-speech feedback:
python main.py

## Project Structure

* `app.py`: The Streamlit web application.
* `main.py`: The command-line interface version.
* `bq_client.py`: Handles BigQuery authentication and execution with safety limits.
* `prompts.py`: Contains the strict schema mapping and system instructions for the LLM.
* `requirements.txt`: Python dependency list.
