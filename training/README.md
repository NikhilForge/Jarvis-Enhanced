# Training & alignment pipeline (all of it fits on an RTX 3050 6GB)

| Step | Script | Runtime | Output |
|---|---|---|---|
| 1. Tool-calling dataset | `gen_tool_dataset.py` | seconds | `data/tools_sft.jsonl` |
| 2. Persona dataset | `gen_persona_dataset.py` | seconds | `data/persona_sft.jsonl` |
| 3. Synthetic edge cases | `synth_edge_cases.py` | minutes (API) | `data/synthetic_sft.jsonl` |
| 4. Preference pairs | `gen_dpo_pairs.py` | seconds | `data/dpo_pairs.jsonl` |
| 5. Custom wake word | `train_wakeword.py` | ~40 min CPU/GPU | `../models/jarvis.onnx` |
| 6. QLoRA SFT | `sft_unsloth.py` | ~50 min on 3050 | `out/jarvis-lora` |
| 7. DPO alignment | `dpo_unsloth.py` | ~25 min | `out/jarvis-dpo` |
| 8. Merge + quantise | `merge_gguf.py` | ~10 min | `out/jarvis-3b-q4_k_m.gguf` |
| 9. Register with Ollama | `Modelfile` | seconds | `ollama create jarvis` |

Then set `llm.model: jarvis` in `../config.yaml`.

Evaluation lives in `../eval/` (WER, tool-call accuracy, persona adherence, latency, VRAM).
