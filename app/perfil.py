"""
Convierte el perfil de un cliente (el jsonb de Supabase) en texto legible
para meterlo dentro de un prompt.

Por qué no se le pasa el JSON crudo al modelo: el JSON crudo con llaves y
comillas compite con el esquema de salida que también son llaves, y el modelo
se confunde. En texto plano con títulos, lo lee mejor y se equivoca menos.

Esta función no sabe nada de odontología. Recorre lo que traiga el perfil, sea
cual sea. Agregar un cliente de otro rubro no exige tocar este archivo.
"""

from typing import Any

# Estas claves se muestran con un nombre bonito; el resto usa su propio nombre
# con guiones bajos convertidos en espacios.
ETIQUETAS = {
    "nombre_marca": "Marca",
    "vocero": "Quién habla a cámara",
    "presentacion_corta": "Presentación (usar tal cual en los guiones)",
    "especialidad": "Especialidad",
    "ubicacion": "Ubicación",
    "zona_de_influencia": "Zona de influencia",
    "credenciales": "Credenciales (las únicas que se pueden mencionar)",
    "diferenciador_principal": "Diferenciador",
    "filosofia": "Filosofía",
    "servicios": "Servicios",
    "precios_publicos": "Precios públicos",
    "financiamiento": "Financiamiento",
    "horario": "Horario",
    "contacto": "Contacto",
    "prueba_social": "Prueba social",
    "redes": "Redes",
    "aviso_cofepris": "Aviso de publicidad COFEPRIS",
    "tono": "Tono de voz",
    "audiencias": "Audiencias",
    "pilares_de_contenido": "Pilares de contenido",
    "ctas_permitidos": "CTAs permitidos (no inventar otros)",
}

# El orden en que conviene que el modelo los lea.
ORDEN = list(ETIQUETAS.keys())


def _valor(v: Any, sangria: int = 0) -> str:
    pad = "  " * sangria
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    if isinstance(v, list):
        partes = []
        for item in v:
            if isinstance(item, dict):
                # Caso de los pilares: {"pilar": ..., "objetivo": ..., "ejemplos": ...}
                resumen = " · ".join(f"{k}: {x}" for k, x in item.items())
                partes.append(f"{pad}- {resumen}")
            else:
                partes.append(f"{pad}- {item}")
        return "\n" + "\n".join(partes)
    if isinstance(v, dict):
        partes = []
        for k, x in v.items():
            nombre = k.replace("_", " ")
            if isinstance(x, list):
                partes.append(f"{pad}- **{nombre}:** {', '.join(str(i) for i in x)}")
            else:
                partes.append(f"{pad}- **{nombre}:** {x}")
        return "\n" + "\n".join(partes)
    return str(v)


def formatear(perfil: dict[str, Any]) -> str:
    """El perfil como texto en Markdown, listo para insertar en un prompt."""
    if not perfil:
        return "(Sin perfil de cliente. No inventes datos de marca ni credenciales.)"

    claves = [k for k in ORDEN if k in perfil]
    claves += [k for k in perfil if k not in ETIQUETAS]

    lineas = []
    for k in claves:
        etiqueta = ETIQUETAS.get(k, k.replace("_", " ").capitalize())
        lineas.append(f"**{etiqueta}:** {_valor(perfil[k])}".rstrip())
    return "\n\n".join(lineas)


def aviso_cofepris(perfil: dict[str, Any]) -> str:
    """El número de aviso, o cadena vacía si el cliente no tiene."""
    return str(perfil.get("aviso_cofepris") or "").strip()
