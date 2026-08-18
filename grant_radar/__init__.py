# Paquete "grant_radar": primer paso de la división en módulos propuesta en
# SUGERENCIAS.MD (3.2). El script principal `Grant-Radar-prueba.py` sigue
# siendo el punto de entrada — su nombre con guiones no se puede importar
# directamente en Python, así que la lógica que se va extrayendo vive aquí,
# en paquetes con nombres válidos, y el script principal la importa.
# No mover aquí nada que dependa de otra parte del script todavía no
# extraída: cada módulo debe poder probarse sin ejecutar el resto del
# pipeline (ver tests/test_grant_radar_parsing_helpers.py).
