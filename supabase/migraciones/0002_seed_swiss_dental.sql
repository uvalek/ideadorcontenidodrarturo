-- ============================================================
-- Primer cliente: SWISS Dental (Dr. Arturo Ramírez Tapia)
--
-- Todo lo que hay aquí sale de drarturotapia.com y de lo que nos pasó el
-- cliente. No se inventó ningún dato: ni nombres de otros doctores del
-- equipo, ni casos, ni cifras de pacientes, ni estudios propios.
--
-- `on conflict (slug) do update` para poder volver a correrlo cuando el
-- perfil cambie, sin crear un duplicado.
--
-- El campo `conocimiento` queda vacío a propósito: ahí va después el contexto
-- adicional sobre cómo habla y qué criterio tiene el doctor.
-- ============================================================

insert into public.contenido_clientes (nombre, slug, perfil, conocimiento, activo)
values (
  'SWISS Dental',
  'swiss-dental',
  '{"nombre_marca": "SWISS Dental", "vocero": "Dr. Arturo Ramírez Tapia", "presentacion_corta": "Soy el Dr. Arturo Ramírez Tapia, ortodoncista certificado con más de 20 años de experiencia y fundador de SWISS Dental en Tlaxcala.", "especialidad": "Ortodoncia y odontología general asistida con microscopio (micro-odontología)", "ubicacion": "Carretera Tlaxcala a Texoloc #31, San Diego Metepec, Tlaxcala", "zona_de_influencia": "Tlaxcala capital, municipios conurbados y zona Puebla", "credenciales": ["Cirujano Dentista, UPAEP (2001)", "Especialista en Ortodoncia, UPAEP (2008)", "Certificado en 2017 y recertificado en 2022 por la Asociación Mexicana de Ortodoncia / Federación de Colegios de Ortodoncistas A.C.", "Fundador (2018) de la primera clínica de odontología general asistida con microscopio en la zona Tlaxcala–Puebla", "Socio activo: Asociación Mexicana de Ortodoncia, Colegio de Ortodoncistas del Estado de Puebla, Asociación Latinoamericana de Ortodoncia, World Federation of Orthodontists, American Association of Orthodontists, Academy of Microscope Enhanced Dentistry"], "diferenciador_principal": "Diagnóstico y tratamientos con microscopio dental: más precisión, mínima invasión, menor tasa de retratamiento", "filosofia": "Enfoque honesto, científico y humano. Decidimos contigo, no por ti. Explicamos con claridad qué está pasando y cuáles son tus opciones.", "servicios": {"ortodoncia": ["Brackets metálicos convencionales", "Brackets de autoligado", "Brackets estéticos (zafiro/cerámicos)", "Alineadores transparentes", "Ortopedia maxilar / ortodoncia interceptiva en niños", "Ortodoncia quirúrgica (con cirujano maxilofacial)", "Reposición de brackets"], "odontologia_general_con_microscopio": ["Consulta y diagnóstico de caries", "Limpieza dental (profilaxis)", "Resinas asistidas con microscopio", "Extracciones simples y complejas", "Muelas del juicio"], "protesis": ["Provisionales", "Prótesis parcial removible", "Prótesis total", "Corona metal-porcelana", "Corona E-MAX", "Incrustaciones inlay/onlay/overlay"], "estetica": ["Blanqueamiento con láser terapéutico (reduce riesgo de sensibilidad)", "Carillas de resina", "Carillas de porcelana"], "otros": ["Urgencias (dolor intenso, infección, traumatismo)", "Consulta en línea (teleodontología)", "Guarda oclusal para bruxismo o post-ortodoncia", "Retoma tu tratamiento de ortodoncia si te mudaste a Tlaxcala"]}, "precios_publicos": {"primera_consulta": "$900 MXN (incluye evaluación con microscopio, cámara intraoral y radiografías digitales si son necesarias)", "cita_de_urgencia": "$1,600 MXN (en horario laboral, independiente del tratamiento)", "nota": "Usar precios solo si el tema lo pide; pueden cambiar"}, "financiamiento": "Meses sin intereses con tarjetas participantes Visa, Mastercard y American Express", "horario": "Lunes a viernes 10:00–14:00 y 16:00–20:00; sábado 10:00–14:00. Consulta previa cita.", "contacto": "WhatsApp 246 144 1431", "prueba_social": "Reseñas de pacientes destacan: amabilidad, paciencia, seguridad, consultorio limpio, puntualidad y actualización constante", "redes": ["Instagram @dr.arturo.ramirez.tapia", "Facebook /swisstlaxcala", "YouTube @swissdental1503", "Doctoralia"], "aviso_cofepris": "2529012002A00051", "tono": "Profesional, cercano y claro. Autoridad sin arrogancia. Educativo antes que vendedor. Español de México, tuteo. Nada de clickbait vacío ni exageraciones.", "audiencias": ["Adultos 20–45 que quieren alinear sus dientes de forma discreta (alineadores, brackets estéticos)", "Mamás y papás con hijos de 6–12 años (ortopedia/ortodoncia interceptiva)", "Personas que dejaron su tratamiento de ortodoncia a medias o se mudaron a Tlaxcala", "Adultos que buscan estética (blanqueamiento, carillas, coronas E-MAX)", "Personas con dolor o miedo al dentista que buscan un trato honesto y poco invasivo"], "pilares_de_contenido": [{"pilar": "Micro-odontología", "objetivo": "Diferenciación", "ejemplos": "Qué ve el microscopio que el ojo no; resina con y sin magnificación; por qué el diagnóstico preciso evita retratamientos"}, {"pilar": "Ortodoncia explicada", "objetivo": "Educación + intención de compra", "ejemplos": "Brackets vs alineadores; autoligado; cuándo llevar a un niño; qué es ortodoncia quirúrgica; qué pasa si no usas retenedor"}, {"pilar": "Mitos y dudas frecuentes", "objetivo": "Alcance", "ejemplos": "¿El blanqueamiento daña? ¿Hay edad límite para brackets? ¿Hay que sacar siempre las muelas del juicio?"}, {"pilar": "Autoridad y confianza", "objetivo": "Credibilidad", "ejemplos": "Qué significa estar certificado y recertificado; cómo elegir ortodoncista; 20 años de práctica"}, {"pilar": "Objeciones y conversión", "objetivo": "Citas", "ejemplos": "Qué incluye la primera consulta; meses sin intereses; retomar tratamiento; qué es una urgencia dental"}, {"pilar": "Detrás de escena humano", "objetivo": "Cercanía", "ejemplos": "Cómo es una primera visita; limpieza y protocolos; el equipo; puntualidad"}], "ctas_permitidos": ["Agenda tu valoración por WhatsApp al 246 144 1431", "Guarda este video para tu próxima visita al dentista", "Comenta tu duda y la respondo en otro video", "Comparte con alguien que está pensando en ponerse brackets"]}'::jsonb,
  '',
  true
)
on conflict (slug) do update
  set nombre = excluded.nombre,
      perfil = excluded.perfil,
      activo = excluded.activo;

-- ── Bucket de imágenes ──────────────────────────────────────
-- Lectura pública: las rutas son UUIDs impredecibles, así la URL se puede
-- pegar en cualquier editor de video sin tener que firmarla. La escritura
-- solo ocurre desde el backend con la service_role key, que salta RLS, así
-- que no hace falta ninguna política de insert.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'contenido-imagenes',
  'contenido-imagenes',
  true,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;
