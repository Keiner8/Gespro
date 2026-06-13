"""Integracion del asistente con Gemini."""

from django.conf import settings


class GeminiSdkError(Exception):
    """Error controlado para la integracion con Gemini."""


def generar_respuesta_gemini(texto, modelo=None):
    try:
        import google.generativeai as genai
    except Exception as exc:
        raise GeminiSdkError(f'No se pudo cargar google-generativeai: {exc}')

    api_key = (getattr(settings, 'GEMINI_API_KEY', '') or '').strip()
    if not api_key:
        raise GeminiSdkError('GEMINI_API_KEY no esta configurada en el servidor')

    genai.configure(api_key=api_key)
    model_name = (modelo or getattr(settings, 'GEMINI_MODEL', '') or 'gemini-1.5-flash').strip()
    prompt = (texto or '').strip()
    if not prompt:
        raise GeminiSdkError('Debes escribir una pregunta.')

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
    except Exception as exc:
        raise GeminiSdkError(f'Gemini fallo al generar respuesta: {exc}')

    return (getattr(response, 'text', '') or '').strip()
