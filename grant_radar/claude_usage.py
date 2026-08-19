# claude_usage.py — recuento de consumo y coste de las llamadas a Claude
#
# Suma tokens y dinero de las respuestas de la API, incluidos los intentos que
# fallaron. Es deliberado: cada respuesta HTTP se contabiliza **antes** de
# validar su JSON, porque un intento con salida truncada ya se ha facturado
# (AGENTS.md sección 5). Un reintento con éxito acumula también el consumo de
# los fallidos, y si la ejecución aborta, `aggregate_aborted_run_usage()`
# reconstruye lo gastado sumando los análisis completos y las etapas
# facturables del caso que falló.
#
# Los precios son los de la tarifa vigente por millón de tokens; cambiarlos
# altera los importes que se registran en la auditoría, no lo que factura
# Anthropic.

# USD por millón de tokens.
CLAUDE_INPUT_USD_PER_MTOK = 1.0
CLAUDE_OUTPUT_USD_PER_MTOK = 5.0
CLAUDE_CACHE_WRITE_USD_PER_MTOK = 1.25
CLAUDE_CACHE_READ_USD_PER_MTOK = 0.10


def aggregate_token_usage(usages: list[dict]) -> dict:
    valid = [usage for usage in usages if isinstance(usage, dict) and usage]
    return {
        "analyzed_convocations": len(valid),
        "api_calls": sum(int(usage.get("api_calls", 2)) for usage in valid),
        "retry_api_calls": sum(
            int(usage.get("retry_api_calls", 0)) for usage in valid
        ),
        "input_tokens": sum(int(usage.get("input_tokens", 0)) for usage in valid),
        "output_tokens": sum(int(usage.get("output_tokens", 0)) for usage in valid),
        "cache_write_tokens": sum(
            int(usage.get("cache_write_tokens", 0)) for usage in valid
        ),
        "cache_read_tokens": sum(
            int(usage.get("cache_read_tokens", 0)) for usage in valid
        ),
        "total_tokens": sum(int(usage.get("total_tokens", 0)) for usage in valid),
        "estimated_cost_usd": round(
            sum(float(usage.get("estimated_cost_usd", 0)) for usage in valid),
            6,
        ),
        "pricing_usd_per_mtok": {
            "input": CLAUDE_INPUT_USD_PER_MTOK,
            "output": CLAUDE_OUTPUT_USD_PER_MTOK,
            "cache_write": CLAUDE_CACHE_WRITE_USD_PER_MTOK,
            "cache_read": CLAUDE_CACHE_READ_USD_PER_MTOK,
        },
        "pricing_note": (
            "Estimación calculada desde usage devuelto por Anthropic; "
            "no incluye impuestos ni posibles ajustes comerciales."
        ),
    }


def aggregate_partial_token_usage(usages: list[dict]) -> dict:
    """Resume etapas completadas antes de abortar una convocatoria."""
    valid = [usage for usage in usages if isinstance(usage, dict) and usage]
    input_tokens = sum(int(usage.get("input_tokens", 0)) for usage in valid)
    output_tokens = sum(int(usage.get("output_tokens", 0)) for usage in valid)
    cache_write_tokens = sum(
        int(usage.get("cache_write_tokens", 0)) for usage in valid
    )
    cache_read_tokens = sum(
        int(usage.get("cache_read_tokens", 0)) for usage in valid
    )
    return {
        "completed_api_calls": sum(
            int(usage.get("api_calls", 1)) for usage in valid
        ),
        "retry_api_calls": sum(
            int(usage.get("retry_api_calls", 0)) for usage in valid
        ),
        "completed_stages": [str(usage.get("stage", "")) for usage in valid],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cache_read_tokens": cache_read_tokens,
        "total_tokens": (
            input_tokens + output_tokens + cache_write_tokens + cache_read_tokens
        ),
        "estimated_cost_usd": round(
            sum(float(usage.get("estimated_cost_usd", 0)) for usage in valid),
            6,
        ),
    }


def aggregate_aborted_run_usage(
    completed_analyses: list[dict],
    failed_analysis_stages: list[dict],
) -> dict:
    """Incluye análisis completos e intentos facturables del caso fallido."""
    completed = aggregate_token_usage(completed_analyses)
    partial = aggregate_partial_token_usage(failed_analysis_stages)
    return {
        "analyzed_convocations": completed["analyzed_convocations"],
        "failed_convocations": int(bool(failed_analysis_stages)),
        "api_calls": completed["api_calls"] + partial["completed_api_calls"],
        "retry_api_calls": (
            completed.get("retry_api_calls", 0)
            + partial.get("retry_api_calls", 0)
        ),
        "completed_analysis_api_calls": completed["api_calls"],
        "failed_analysis_api_calls": partial["completed_api_calls"],
        "failed_analysis_stages": partial["completed_stages"],
        "input_tokens": completed["input_tokens"] + partial["input_tokens"],
        "output_tokens": completed["output_tokens"] + partial["output_tokens"],
        "cache_write_tokens": (
            completed["cache_write_tokens"] + partial["cache_write_tokens"]
        ),
        "cache_read_tokens": (
            completed["cache_read_tokens"] + partial["cache_read_tokens"]
        ),
        "total_tokens": completed["total_tokens"] + partial["total_tokens"],
        "estimated_cost_usd": round(
            completed["estimated_cost_usd"] + partial["estimated_cost_usd"], 6
        ),
        "pricing_usd_per_mtok": completed["pricing_usd_per_mtok"],
        "pricing_note": completed["pricing_note"],
    }
