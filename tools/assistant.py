"""Assistant-level tools: document RAG, reminders, routines and learning stats."""
from tools.registry import tool
from core.bus import BUS


@tool("docs.search", "Search the operator's indexed documents and notes for an answer.",
      {"query": {"type": "string", "description": "what to look for"}})
def docs_search(query, ctx=None):
    rag = getattr(ctx, "rag", None) if not isinstance(ctx, dict) else ctx.get("rag")
    if not rag or not rag.available():
        return "document index unavailable"
    hits = rag.search(query)
    return "\n\n".join(f"[{h['path']}] {h['text'][:500]}" for h in hits) or "no matches"


@tool("docs.reindex", "Re-scan the configured folders and rebuild the document index.", {})
def docs_reindex(ctx=None):
    rag = getattr(ctx, "rag", None) if not isinstance(ctx, dict) else ctx.get("rag")
    if not rag:
        return "document index unavailable"
    return f"indexed {rag.index()} chunks"


@tool("reminder.set", "Remind the operator out loud after a delay in minutes.",
      {"minutes": {"type": "number"}, "text": {"type": "string"}})
def reminder_set(minutes, text, ctx=None):
    pro = getattr(ctx, "proactive", None) if not isinstance(ctx, dict) else ctx.get("proactive")
    if not pro:
        return "scheduler unavailable"
    pro.schedule_in(float(minutes) * 60, text)
    return f"reminder set for {minutes} minutes"


@tool("routine.daily", "Create a spoken daily routine at a 24h HH:MM local time.",
      {"time": {"type": "string", "description": "HH:MM"}, "text": {"type": "string"}})
def routine_daily(time, text, ctx=None):
    pro = getattr(ctx, "proactive", None) if not isinstance(ctx, dict) else ctx.get("proactive")
    if not pro:
        return "scheduler unavailable"
    pro.schedule_daily(time, text)
    return f"daily routine armed for {time}"


@tool("reminder.list", "List everything currently scheduled.", {})
def reminder_list(ctx=None):
    pro = getattr(ctx, "proactive", None) if not isinstance(ctx, dict) else ctx.get("proactive")
    if not pro:
        return "scheduler unavailable"
    jobs = pro.pending()
    return "; ".join(f"{j.text}" for j in jobs) or "nothing scheduled"


@tool("learning.stats", "Report how much live training data has been collected.", {})
def learning_stats(ctx=None):
    l = getattr(ctx, "learning", None) if not isinstance(ctx, dict) else ctx.get("learning")
    if not l:
        return "learning loop disabled"
    s = l.stats()
    BUS.emit("learn", f"{s['sft']} SFT rows · {s['dpo']}/{s['target']} DPO pairs")
    return str(s)
