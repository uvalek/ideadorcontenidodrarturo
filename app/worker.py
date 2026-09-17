"""
El worker: revisa la tabla `generaciones` y procesa lo que esté pendiente.

Es un bucle asyncio dentro del mismo contenedor del API, sin Redis ni Celery.
Para dos socios pidiendo un par de temas al día, una cola en Postgres es
suficiente y es una pieza menos que mantener.

Dos cosas lo hacen sobrevivir a un reinicio:

  - Mientras trabaja escribe `latido_en` en cada cambio de paso.
  - Al arrancar, y cada minuto, busca generaciones cuyo latido se detuvo y las
    marca como error para que se puedan reintentar. Sin esto, un reinicio a
    media generación dejaría la fila girando en "generando_piezas" para
    siempre, que es justo lo que pasaba con el polling del workflow de n8n.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app import db, flujo
from app.config import ajustes

log = logging.getLogger("worker")

ESPERA_ENTRE_VUELTAS = 5.0
CADA_CUANTO_RESCATAR = 60.0
MINUTOS_PARA_DAR_POR_MUERTA = 5

# Las generaciones que este proceso tiene ahora mismo entre manos.
_en_curso: set[str] = set()


async def procesar(fila: dict[str, Any]) -> None:
    gid = fila["id"]
    _en_curso.add(gid)
    try:
        cliente = db.obtener_cliente_contenido(fila["cliente_id"])
        if not cliente:
            db.actualizar_generacion(
                gid,
                estado="error",
                error_msg="El cliente de esta generación ya no existe.",
            )
            return

        perfil = cliente.get("perfil") or {}
        conocimiento = (cliente.get("conocimiento") or "").strip()

        encargo = flujo.Encargo(
            tema=fila["tema"],
            perfil=perfil,
            conocimiento=conocimiento,
            audiencia=fila.get("audiencia") or "",
            plataforma=fila.get("plataforma") or "ambas",
            num_ideas=fila.get("num_ideas") or 5,
            usar_investigacion=bool(fila.get("usar_investigacion")),
        )

        async def avisar(estado: str, progreso: int, detalle: str) -> None:
            # El estado 'completado' lo escribe el cierre de abajo, junto con
            # los tokens, para no dejar la fila completada un instante antes
            # de que los resultados estén guardados.
            if estado != "completado":
                db.latir(gid, estado, progreso, detalle)

        resultado = await flujo.correr(encargo, avisar)

        # Se guarda todo antes de marcar completado.
        db.actualizar_generacion(
            gid,
            investigacion=resultado.investigacion,
            # El resumen estratégico (por cuál empezar, en qué orden publicar)
            # viene junto a las ideas pero no pertenece a ninguna, así que vive
            # en la generación.
            resumen=(resultado.ideas or {}).get("resumen_estrategico") or {},
            latido_en=db.ahora(),
        )

        for posicion, pieza in enumerate(resultado.piezas, start=1):
            idea_id = db.guardar_idea(gid, posicion, pieza.idea)
            for tipo, datos in (
                ("tiktok", pieza.guion),
                ("youtube", pieza.intros),
                ("ganchos", pieza.ganchos),
                ("prompts_imagen", pieza.prompts_imagen),
            ):
                error = pieza.errores.get(
                    {"tiktok": "guion", "youtube": "intros"}.get(tipo, tipo)
                )
                if datos or error:
                    db.guardar_pieza(idea_id, tipo, datos, error)

        avisos = list(resultado.advertencias)
        for i, pieza in enumerate(resultado.piezas, start=1):
            avisos += [f"Idea {i}: {a}" for a in pieza.advertencias]

        db.actualizar_generacion(
            gid,
            estado="completado",
            progreso=100,
            detalle="Listo",
            advertencias=avisos,
            tokens_entrada=resultado.tokens_entrada,
            tokens_salida=resultado.tokens_salida,
            error_msg=None,
            latido_en=db.ahora(),
        )
        log.info("Generación %s completada", gid)

    except Exception as fallo:  # noqa: BLE001 — cualquier fallo debe quedar visible
        log.exception("Generación %s falló", gid)
        db.actualizar_generacion(
            gid, estado="error", error_msg=_legible(fallo), latido_en=db.ahora()
        )
    finally:
        _en_curso.discard(gid)


def _legible(fallo: Exception) -> str:
    """Traduce los fallos más comunes a algo que se pueda leer sin ser técnico."""
    texto = str(fallo)
    if "401" in texto or "invalid_api_key" in texto.lower():
        return (
            "La llave de OpenAI no es válida o caducó. Revísala en las "
            "variables de entorno del servidor."
        )
    if "429" in texto or "rate limit" in texto.lower():
        return (
            "Se alcanzó el límite de peticiones del proveedor. Espera unos "
            "minutos y reintenta."
        )
    if "insufficient_quota" in texto.lower():
        return "La cuenta de OpenAI se quedó sin saldo."
    if "timeout" in texto.lower() or "timed out" in texto.lower():
        return "El proveedor tardó demasiado en responder. Puedes reintentar."
    return texto[:500]


async def bucle() -> None:
    """Corre para siempre. Se arranca desde main.py al levantar el API."""
    # Si esto falla, el worker no puede trabajar. Se avisa fuerte y se reintenta
    # en cada vuelta en vez de morir en silencio: un API vivo con el worker
    # muerto es peor que un error, porque las generaciones se quedarían
    # "pendiente" para siempre sin que nada lo dijera.
    try:
        rescatadas = db.rescatar_colgadas(MINUTOS_PARA_DAR_POR_MUERTA)
        log.info("Worker en marcha")
        if rescatadas:
            log.warning(
                "%d generación(es) quedaron a medias por un reinicio y se "
                "marcaron como error: %s",
                len(rescatadas),
                ", ".join(rescatadas),
            )
    except Exception:  # noqa: BLE001
        log.exception(
            "El worker no pudo conectarse a Supabase. Revisa SUPABASE_URL y "
            "SUPABASE_SERVICE_ROLE_KEY. Reintentando en cada vuelta."
        )

    desde_ultimo_rescate = 0.0

    while True:
        try:
            if desde_ultimo_rescate >= CADA_CUANTO_RESCATAR:
                db.rescatar_colgadas(MINUTOS_PARA_DAR_POR_MUERTA)
                desde_ultimo_rescate = 0.0

            if len(_en_curso) < ajustes.max_generaciones_activas:
                fila = db.siguiente_pendiente()
                if fila and db.tomar(fila["id"]):
                    asyncio.create_task(procesar(fila))

        except Exception:  # noqa: BLE001 — el bucle nunca debe morir
            log.exception("Error en el bucle del worker")

        await asyncio.sleep(ESPERA_ENTRE_VUELTAS)
        desde_ultimo_rescate += ESPERA_ENTRE_VUELTAS
