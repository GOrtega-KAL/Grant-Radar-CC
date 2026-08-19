# publishing.py — publicación del JSON en GitHub Pages
#
# Sube `convocatorias.json` al repositorio mediante la API REST de GitHub; la
# página lo sirve actualizado sin más pasos. Solo se invoca al final de una
# ejecución completa correcta: una ejecución que aborta no publica nada.
#
# **Las credenciales se reciben como parámetros, nunca se leen aquí.** El
# script principal es el único que carga `GITHUB_TOKEN` desde `.env` o del
# entorno (ver AGENTS.md sección 7), y este módulo se limita a usar lo que le
# pasen. Así un módulo del paquete no toca secretos ni puede filtrarlos por
# error en un log.
#
# `github_token_format_is_valid()` es solo una comprobación de forma: un token
# con formato correcto puede estar caducado o revocado. La validez real solo se
# conoce al autenticar contra GitHub.

import base64
import os
from datetime import datetime

import requests


def github_token_format_is_valid(token: str) -> bool:
    """Validación local de los formatos habituales de token de GitHub."""
    return (
        isinstance(token, str)
        and token == token.strip()
        and token.startswith(("github_pat_", "ghp_"))
        and len(token) >= 40
    )


def github_upload(
    filepath: str,
    *,
    token: str,
    user: str,
    repo: str,
    branch: str,
):
    """
    Sube el convocatorias.json al repositorio GitHub usando la API REST.
    GitHub Pages servirá automáticamente el archivo actualizado.
    """
    if not github_token_format_is_valid(token):
        print("⚠ Formato de GITHUB_TOKEN no válido — se omite la publicación")
        return

    filename = os.path.basename(filepath)
    url      = f"https://api.github.com/repos/{user}/{repo}/contents/{filename}"
    headers  = {
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
    }

    # Leer el archivo y codificarlo en base64 (requerido por GitHub API)
    with open(filepath, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Obtener el SHA actual del archivo (necesario para actualizar, no para crear)
    sha = None
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json().get("sha")

    # Subir o actualizar el archivo
    payload = {
        "message": f"Grant-Radar: actualización automática {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
        "content": content_b64,
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha  # necesario para sobreescribir un archivo existente

    resp = requests.put(url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        print(f"✓ convocatorias.json subido a GitHub Pages")
        print(f"  URL pública: https://{user}.github.io/{repo}/convocatorias.json")
    else:
        print(f"⚠ Error subiendo a GitHub: {resp.status_code} — {resp.json().get('message','')}")
