"""Integracion del asistente con Gemini."""

from django.conf import settings


class GeminiSdkError(Exception):
    """Error controlado para la integracion con Gemini."""


def _build_contextual_prompt(texto: str, historial: list[dict] | None = None) -> str:
    historial = historial or []
    partes = [
        'Eres el asistente virtual de GESPRO.',
        'Responde en espanol, de forma clara y manteniendo continuidad con la conversacion.',
        'Si el usuario pide "hazlo igual", "lo anterior", "con la misma estructura" o algo parecido, usa el historial como referencia.',
    ]

    if historial:
        partes.append('\nHistorial reciente de la conversacion:')
        for index, item in enumerate(historial[-6:], start=1):
            pregunta = (item.get('pregunta') or '').strip()
            respuesta = (item.get('respuesta') or '').strip()
            if pregunta:
                partes.append(f'Usuario {index}: {pregunta}')
            if respuesta:
                partes.append(f'Asistente {index}: {respuesta}')

    partes.append('\nNueva pregunta del usuario:')
    partes.append(texto.strip())
    return '\n'.join(partes)


def generar_respuesta_gemini(texto, modelo=None, historial=None):
    try:
        import google.generativeai as genai
    except Exception as exc:
        raise GeminiSdkError(f'No se pudo cargar google-generativeai: {exc}')

    api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if not api_key:
        raise GeminiSdkError('GEMINI_API_KEY no esta configurada en el servidor')

    genai.configure(api_key=api_key)
    model_name = (modelo or getattr(settings, 'GEMINI_MODEL', '') or 'gemini-1.5-flash').strip()
    pregunta = (texto or '').strip()
    if not pregunta:
        raise GeminiSdkError('Debes escribir una pregunta.')
    prompt = _build_contextual_prompt(pregunta, historial)

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
    except Exception as exc:
        raise GeminiSdkError(f'Gemini fallo al generar respuesta: {exc}')

    return (getattr(response, 'text', '') or '').strip()
