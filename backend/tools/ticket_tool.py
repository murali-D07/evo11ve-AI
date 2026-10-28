import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "tickets.json"


def raise_ticket(summary: str, category: str, user_message: str) -> dict[str, str]:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tickets = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else []
    ticket = {
        "id": f"EV-{uuid4().hex[:8].upper()}",
        "status": "open",
        "category": category,
        "summary": summary,
        "user_message": user_message,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    tickets.append(ticket)
    DATA_FILE.write_text(json.dumps(tickets, indent=2), encoding="utf-8")
    return {"ok": "true", "ticket_id": ticket["id"], "status": "open"}
