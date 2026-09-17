"""
Prueba el worker contra la base real: encola un tema y mira cómo se llena solo.

    python scripts/probar_worker.py
    python scripts/probar_worker.py --tema "Qué ve un microscopio dental" --ideas 1

Levanta el worker en este mismo proceso, así que sirve para probar en local
exactamente lo que va a correr en el VPS.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import db, worker  # noqa: E402

TEMA = "Qué ve un microscopio dental que el ojo no puede ver"


async def principal() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tema", default=TEMA)
    p.add_argument("--ideas", type=int, default=1)
    p.add_argument("--cliente", default="swiss-dental")
    args = p.parse_args()

    cliente = (
        db.cliente()
        .table("contenido_clientes")
        .select("id, nombre")
        .eq("slug", args.cliente)
        .maybe_single()
        .execute()
    )
    if not cliente or not cliente.data:
        print(f"❌ No existe el cliente «{args.cliente}».")
        return 1

    fila = (
        db.cliente()
        .table("contenido_generaciones")
        .insert(
            {
                "cliente_id": cliente.data["id"],
                "tema": args.tema,
                "num_ideas": args.ideas,
                "usar_investigacion": True,
                "estado": "pendiente",
            }
        )
        .execute()
    )
    gid = fila.data[0]["id"]

    print(f"\n  Cliente:    {cliente.data['nombre']}")
    print(f"  Tema:       {args.tema}")
    print(f"  Generación: {gid}")
    print(f"\n  Encolada como 'pendiente'. Arrancando el worker…\n")

    tarea = asyncio.create_task(worker.bucle())
    arranque = time.monotonic()
    ultimo = None

    try:
        while time.monotonic() - arranque < 900:
            await asyncio.sleep(3)
            g = db.obtener_generacion(gid)
            if not g:
                print("  La generación desapareció.")
                return 1

            marca = (g["estado"], g["progreso"], g.get("detalle", ""))
            if marca != ultimo:
                ultimo = marca
                print(
                    f"  [{g['progreso']:3d}%] {g['estado']:18} {g.get('detalle') or ''}"
                )

            if g["estado"] == "completado":
                return await _informe(gid, g, time.monotonic() - arranque)
            if g["estado"] == "error":
                print(f"\n❌ Error: {g.get('error_msg')}\n")
                return 1

        print("\n⏱  Se acabó el tiempo de espera.")
        return 1
    finally:
        tarea.cancel()


async def _informe(gid: str, g: dict, segundos: float) -> int:
    ideas = (
        db.cliente()
        .table("contenido_ideas")
        .select("id, orden, data")
        .eq("generacion_id", gid)
        .order("orden")
        .execute()
    ).data or []

    print(f"\n  ── Lo que quedó guardado ──\n")
    print(f"  Tiempo:        {segundos:.0f} s")
    print(f"  Investigación: {len(g.get('investigacion') or '')} caracteres")
    print(f"  Tokens:        {g['tokens_entrada']:,} entrada + {g['tokens_salida']:,} salida")

    for idea in ideas:
        piezas = (
            db.cliente()
            .table("contenido_piezas")
            .select("tipo, estado, error_msg")
            .eq("idea_id", idea["id"])
            .execute()
        ).data or []
        titulo = (idea["data"] or {}).get("titulo", "")
        print(f"\n  Idea {idea['orden']}: {titulo[:60]}")
        for pieza in sorted(piezas, key=lambda x: x["tipo"]):
            estado = "✓" if pieza["estado"] == "completado" else "✗"
            extra = f"  {pieza['error_msg'][:60]}" if pieza.get("error_msg") else ""
            print(f"    {estado} {pieza['tipo']}{extra}")

    avisos = g.get("advertencias") or []
    if avisos:
        print("\n  Advertencias:")
        for a in avisos:
            print(f"    · {a}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
