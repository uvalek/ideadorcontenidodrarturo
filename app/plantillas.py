"""
Carga los prompts de la carpeta `prompts/` y les sustituye las variables.

Las variables van con doble llave: {{tema}}, {{perfil_cliente}}. Se usa doble
y no simple porque los prompts llevan dentro esquemas JSON llenos de llaves
simples, y un `str.format()` normal se atragantaría con ellos.

Hay dos bloques comunes que se insertan solos en cualquier plantilla que los
mencione: {{cumplimiento}} y {{salida_json}}. Viven en `prompts/comun/` y se
editan en un solo lugar para los seis agentes.
"""

import json
import re
from pathlib import Path
from typing import Any

RAIZ_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

_cache: dict[str, str] = {}


def _leer(ruta: Path) -> str:
    clave = str(ruta)
    if clave not in _cache:
        _cache[clave] = ruta.read_text(encoding="utf-8")
    return _cache[clave]


def limpiar_cache() -> None:
    """Para que editar un .md se note sin reiniciar el contenedor."""
    _cache.clear()


def _sustituir(texto: str, variables: dict[str, Any]) -> str:
    def reemplazo(m: re.Match[str]) -> str:
        nombre = m.group(1).strip()
        if nombre not in variables:
            # Se deja tal cual: es más fácil detectar un hueco que perseguir
            # un prompt al que le faltó un dato en silencio.
            return m.group(0)
        v = variables[nombre]
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False, indent=2)
        return str(v)

    return re.sub(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", reemplazo, texto)


def construir(nombre: str, **variables: Any) -> str:
    """
    Devuelve el prompt de `prompts/<nombre>.md` con todo sustituido.

    Los bloques comunes se resuelven primero, para que las variables que
    contienen (como {{aviso_cofepris}}) también se sustituyan.
    """
    texto = _leer(RAIZ_PROMPTS / f"{nombre}.md")

    comunes = {
        "cumplimiento": _leer(RAIZ_PROMPTS / "comun" / "cumplimiento.md"),
        "salida_json": _leer(RAIZ_PROMPTS / "comun" / "salida_json.md"),
    }
    texto = _sustituir(texto, comunes)
    return _sustituir(texto, variables)
