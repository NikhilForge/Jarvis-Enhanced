"""QLoRA supervised fine-tune of Llama 3.2 3B on an RTX 3050 6GB (Unsloth, 4-bit).

    python sft_unsloth.py --epochs 2

Unsloth's fused attention + gradient checkpointing keeps peak VRAM around 4.8 GB.
Only the LoRA adapters (r=16, ~0.6% of weights) are updated.
"""
import argparse, glob, json, os

def load_rows():
    rows = []
    for p in glob.glob("data/*_sft.jsonl"):
        rows += [json.loads(l) for l in open(p, encoding="utf-8")]
    print(f"{len(rows)} training examples from {len(glob.glob('data/*_sft.jsonl'))} files")
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--out", default="out/jarvis-lora")
    ap.add_argument("--max-seq", type=int, default=2048)
    a = ap.parse_args()

    from unsloth import FastLanguageModel
    from datasets import Dataset
    from trl import SFTTrainer, SFTConfig

    model, tok = FastLanguageModel.from_pretrained(
        a.base, max_seq_length=a.max_seq, load_in_4bit=True, dtype=None)
    model = FastLanguageModel.get_peft_model(
        model, r=16, lora_alpha=32, lora_dropout=0.0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=42)

    rows = load_rows()
    ds = Dataset.from_list([{"text": tok.apply_chat_template(r["messages"], tokenize=False)} for r in rows])

    SFTTrainer(
        model=model, tokenizer=tok, train_dataset=ds,
        args=SFTConfig(
            per_device_train_batch_size=1, gradient_accumulation_steps=8,
            num_train_epochs=a.epochs, learning_rate=2e-4, warmup_ratio=0.03,
            logging_steps=10, optim="adamw_8bit", lr_scheduler_type="cosine",
            fp16=True, seed=42, output_dir=a.out, dataset_text_field="text",
            max_seq_length=a.max_seq, save_strategy="epoch", report_to="none"),
    ).train()

    model.save_pretrained(a.out); tok.save_pretrained(a.out)
    print(f"LoRA adapters → {a.out}")

if __name__ == "__main__":
    os.makedirs("out", exist_ok=True); main()
