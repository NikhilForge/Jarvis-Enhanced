"""DPO alignment: mathematically penalise unsafe / hallucinated OS commands.

    python dpo_unsloth.py

Runs on the SFT adapters, so the model keeps its skills but learns to prefer the
'chosen' (valid, reversible, in-schema) command over the 'rejected' one.
"""
import argparse, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapters", default="out/jarvis-lora")
    ap.add_argument("--base", default="unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
    ap.add_argument("--out", default="out/jarvis-dpo")
    ap.add_argument("--beta", type=float, default=0.1)
    a = ap.parse_args()

    from unsloth import FastLanguageModel, PatchDPOTrainer
    PatchDPOTrainer()
    from datasets import Dataset
    from trl import DPOTrainer, DPOConfig

    model, tok = FastLanguageModel.from_pretrained(
        a.adapters if os.path.exists(a.adapters) else a.base,
        max_seq_length=1024, load_in_4bit=True, dtype=None)
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=32, use_gradient_checkpointing="unsloth", random_state=42)

    rows = [json.loads(l) for l in open("data/dpo_pairs.jsonl", encoding="utf-8")]
    ds = Dataset.from_list(rows)

    DPOTrainer(
        model=model, ref_model=None, tokenizer=tok, train_dataset=ds,
        args=DPOConfig(beta=a.beta, per_device_train_batch_size=1,
                       gradient_accumulation_steps=8, num_train_epochs=1,
                       learning_rate=5e-6, optim="adamw_8bit", fp16=True,
                       logging_steps=10, output_dir=a.out, report_to="none",
                       max_length=1024, max_prompt_length=512),
    ).train()

    model.save_pretrained(a.out); tok.save_pretrained(a.out)
    print(f"aligned adapters → {a.out}")

if __name__ == "__main__":
    main()
