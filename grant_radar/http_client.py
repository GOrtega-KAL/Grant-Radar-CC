# http_client.py — cliente HTTP público común a todas las fuentes
#
# Un único GET con reintentos acotados, cabeceras propias y límite opcional de
# tamaño de descarga, más la comprobación de que una URL documental es HTTPS
# pública antes de descargarla. Lo usan BDNS, ECCP, EEN, IDAE y la capa de
# documentos oficiales.
#
# `_http_get()` nunca disfraza un fallo de éxito: devuelve None cuando agota
# los reintentos, y quien llama decide si eso degrada la fuente. Sin caché,
# sin reglas de negocio, sin Claude.

import ipaddress
import logging
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger("grant_radar")


HTTP_USER_AGENT = "GrantRadar-Kalfrisa/3.0 (+public-funding-monitor)"


def _http_get(
    url: str,
    *,
    params: dict | None = None,
    session: requests.Session | None = None,
    timeout: int = 30,
    retries: int = 3,
    headers: dict | None = None,
    max_bytes: int | None = None,
) -> requests.Response | None:
    """GET público con reintentos acotados; nunca oculta un fallo como éxito."""
    client = session or requests
    request_headers = {
        "User-Agent": HTTP_USER_AGENT,
        "Accept-Language": "es,en;q=0.8",
        **(headers or {}),
    }
    for attempt in range(retries):
        try:
            response = client.get(
                url,
                params=params,
                headers=request_headers,
                timeout=timeout,
                allow_redirects=True,
                stream=max_bytes is not None,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            if max_bytes is not None:
                declared_size = response.headers.get("content-length", "")
                if declared_size.isdigit() and int(declared_size) > max_bytes:
                    response.close()
                    log.warning(
                        f"Descarga omitida por tamaño ({declared_size} bytes): {url}"
                    )
                    return None
                chunks = []
                downloaded = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        response.close()
                        log.warning(
                            f"Descarga interrumpida al superar {max_bytes} bytes: {url}"
                        )
                        return None
                    chunks.append(chunk)
                response._content = b"".join(chunks)
                response._content_consumed = True
            return response
        except requests.RequestException as exc:
            if attempt + 1 >= retries:
                log.warning(f"HTTP agotado para {url}: {exc}")
                return None
            time.sleep(0.6 * (2 ** attempt))
    return None


def _is_safe_public_https_url(value: str) -> bool:
    """Limita las descargas documentales a HTTPS público; evita SSRF local."""
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").strip("[]").casefold()
    if parsed.scheme != "https" or not host:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return address.is_global
