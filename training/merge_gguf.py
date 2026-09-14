"""Merge LoRA into the base weights and quantise to q4_K_M GGUF for llama.cpp / Ollama."""
import argparse, subprocess, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapters", default="out/jarvis-dpo")
    ap.add_argument("--base", default="unsloth/Llama-3.2-3B-Instruct")
    ap.add_argument("--out", default="out/jarvis-3b-q4_k_m.gguf")
    a = ap.parse_args()

    from unsloth import FastLanguageModel
    model, tok = FastLanguageModel.from_pretrained(a.adapters, max_seq_length=4096, load_in_4bit=False)
    print("merging adapters into fp16 weights…")
    model.save_pretrained_merged("out/jarvis-3b-merged", tok, save_method="merged_16bit")
    print("quantising to q4_K_M…")
    model.save_pretrained_gguf("out/jarvis-gguf", tok, quantization_method="q4_k_m")
    print(f"done. Register it:\n  ollama create jarvis -f Modelfile\n  # then set llm.model: jarvis in config.yaml")

if __name__ == "__main__":
    main()
