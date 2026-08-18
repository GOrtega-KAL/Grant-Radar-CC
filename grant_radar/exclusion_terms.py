# exclusion_terms.py — carga las listas de palabras de exclusion_terms.json
#
# Lee grant_radar/exclusion_terms.json y expone cada lista como una
# constante en MAYÚSCULAS, lista para usar en Grant-Radar-prueba.py.
# El objetivo es que ampliar una categoría existente (añadir una palabra a
# "transport_terms", por ejemplo) sea editar ese JSON, no tocar Python.
#
# _hard_out_of_scope() sigue decidiendo en Python CUÁNDO se aplica cada
# lista (qué tags térmicos la neutralizan, qué mensaje de descarte usa):
# eso es lógica de negocio con muchas condiciones distintas por categoría
# (ver AGENTS.md, secciones 4 y 13-20) y no es solo una lista de palabras,
# así que no se ha movido aquí en este primer paso.

import json
from pathlib import Path

_TERMS_FILE = Path(__file__).parent / "exclusion_terms.json"

with open(_TERMS_FILE, "r", encoding="utf-8") as _f:
    _DATA = json.load(_f)

TRANSPORT_TERMS = tuple(_DATA["transport_terms"])
BUILDING_TERMS = tuple(_DATA["building_terms"])
CYBERSECURITY_TERMS = tuple(_DATA["cybersecurity_terms"])
CIVIL_SECURITY_TERMS = tuple(_DATA["civil_security_terms"])
GOVERNANCE_PRIMARY_TERMS = tuple(_DATA["governance_primary_terms"])
RENEWABLE_GENERATION_TERMS = tuple(_DATA["renewable_generation_terms"])
NUCLEAR_TERMS = tuple(_DATA["nuclear_terms"])
MARINE_POLICY_TERMS = tuple(_DATA["marine_policy_terms"])
GENERIC_DIGITAL_POLICY_TERMS = tuple(_DATA["generic_digital_policy_terms"])
EDUCATION_HEALTH_TERMS = tuple(_DATA["education_health_terms"])
