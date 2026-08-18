# kalfrisa_profile.py — perfil de cliente para el análisis de Claude
#
# Lee grant_radar/kalfrisa_profile.txt: el texto de contexto sobre Kalfrisa
# que se envía en cada prompt de evaluación (identidad, capacidades
# tecnológicas, programas de interés, qué queda fuera de foco). Es la parte
# de la "configuración por cliente" que SUGERENCIAS.MD (2.7) señala como
# embebida en el código; ahora es un archivo de texto plano que se puede
# editar sin tocar Python. Cambiar su contenido no invalida la caché por sí
# solo — para eso sigue existiendo PROFILE_VERSION en Grant-Radar-prueba.py,
# que hay que subir a mano cuando el cambio de perfil deba forzar reanálisis.

from pathlib import Path

_PROFILE_FILE = Path(__file__).parent / "kalfrisa_profile.txt"

with open(_PROFILE_FILE, "r", encoding="utf-8") as _f:
    # El prompt original empezaba con una línea en blanco (era una cadena
    # """ multilínea en Python); se reproduce aquí para no cambiar el texto
    # que recibe Claude.
    KALFRISA_PROFILE = "\n" + _f.read()
