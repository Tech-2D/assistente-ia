from app.agenda_classes import FIXED_CLASSES
from app.db import read_connection


async def list_classes() -> list[str]:
    async with read_connection() as conn:
        rows = await conn.fetch(
            "SELECT id FROM tech2d.visao_documentos_catalogo WHERE collection='agendaClasses' AND data->>'active'='true' AND data->>'name'=id ORDER BY id"
        )
        return sorted(set(FIXED_CLASSES).union(r["id"] for r in rows), key=str.casefold)
