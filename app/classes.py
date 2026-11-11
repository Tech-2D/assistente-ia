from app.agenda_classes import FIXED_CLASSES
from app.db import read_connection


async def list_classes() -> list[str]:
    async for conn in read_connection():
        rows = await conn.fetch(
            "SELECT id FROM tech2d.catalog_documents WHERE collection='agendaClasses' AND data->>'active'='true' AND data->>'name'=id ORDER BY id"
        )
        return sorted(set(FIXED_CLASSES).union(r["id"] for r in rows), key=str.casefold)
