from huggingface_hub import hf_hub_download

print("Downloading Llama 3 (4.7 GB). This might take a few minutes...")

hf_hub_download(
    repo_id="QuantFactory/Meta-Llama-3-8B-Instruct-GGUF",
    filename="Meta-Llama-3-8B-Instruct.Q4_K_M.gguf",
    local_dir=".", 
    local_dir_use_symlinks=False
)

print("Download complete!")