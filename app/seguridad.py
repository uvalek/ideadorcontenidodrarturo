"""
Quién puede usar este API.

El panel manda el token de la sesión de Supabase en la cabecera
`Authorization: Bearer ...`. Aquí se cambia ese token por el usuario al que
pertenece, preguntándole al propio Supabase, y se comprueba que su correo esté
en ADMIN_EMAILS.

Por qué se pregunta a Supabase en vez de verificar la firma del token aquí:
Supabase rota sus llaves de firma y soporta varios algoritmos, así que
validarlo en local significa mantener un cliente de JWKS al día. Preguntar
cuesta una petición HTTP que se cachea cinco minutos, y no hay nada que
mantener. Este API recibe unas pocas llamadas al día.

Este servicio gasta dinero en cada llamada, así que por defecto todo está
cerrado: cualquier ruta que no diga explícitamente lo contrario exige sesión.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, status

from app.config import ajustes

# token -> (correo, cuándo caduca en el caché)
_cache: dict[str, tuple[str, float]] = {}
VIGENCIA_CACHE = 300.0


async def _correo_del_token(token: str) -> str | None:
    ahora = time.monotonic()

    guardado = _cache.get(token)
    if guardado and guardado[1] > ahora:
        return guardado[0]

    if not ajustes.supabase_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servidor no tiene configurada la conexión con Supabase. "
            "Revisa las variables de entorno.",
        )

    try:
        async with httpx.AsyncClient() as cliente:
            r = await cliente.get(
                f"{ajustes.supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": ajustes.supabase_service_role_key,
                },
                timeout=httpx.Timeout(15.0),
            )
    except httpx.HTTPError as fallo:
        # Un problema de red no es una sesión inválida: si devolviéramos 401,
        # el panel mandaría al usuario a iniciar sesión otra vez sin motivo.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No se pudo verificar tu sesión porque Supabase no respondió. "
            "Vuelve a intentarlo en un momento.",
        ) from fallo

    if r.status_code != 200:
        return None

    correo = (r.json().get("email") or "").lower()
    if correo:
        _cache[token] = (correo, ahora + VIGENCIA_CACHE)
        # El caché se limpia solo: sin esto crecería para siempre.
        if len(_cache) > 200:
            for t, (_, caduca) in list(_cache.items()):
                if caduca <= ahora:
                    _cache.pop(t, None)
    return correo or None


async def socio(authorization: str = Header(default="")) -> dict[str, Any]:
    """Dependencia de FastAPI: deja pasar solo a los correos autorizados."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta la sesión. Vuelve a entrar al panel.",
        )

    token = authorization[7:].strip()
    correo = await _correo_del_token(token)

    if not correo:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "La sesión caducó. Vuelve a entrar al panel.",
        )

    if correo not in ajustes.correos_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Esta cuenta no tiene permiso para generar contenido.",
        )

    return {"correo": correo}


SocioActual = Depends(socio)
