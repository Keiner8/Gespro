"""Vistas del asistente virtual renderizadas por servidor."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.cuentas.views import login_required, role_required

from .forms import AssistantPromptForm
from .services import GeminiSdkError, generar_respuesta_gemini

ASSISTANT_HISTORY_SESSION_KEY = 'gespro_assistant_history'
ASSISTANT_HISTORY_LIMIT = 6


@login_required
@role_required('administrador')
def assistant_home(request: HttpRequest) -> HttpResponse:
    respuesta = ''
    historial = request.session.get(ASSISTANT_HISTORY_SESSION_KEY, [])
    form = AssistantPromptForm(request.POST or None)
    if request.method == 'POST' and request.POST.get('action') == 'clear_history':
        request.session.pop(ASSISTANT_HISTORY_SESSION_KEY, None)
        request.session.modified = True
        messages.success(request, 'Conversacion eliminada correctamente.')
        return redirect('assistant:home')
    if request.method == 'POST' and form.is_valid():
        pregunta = form.cleaned_data['texto']
        try:
            respuesta = generar_respuesta_gemini(pregunta, historial=historial)
            historial.append({'pregunta': pregunta, 'respuesta': respuesta})
            request.session[ASSISTANT_HISTORY_SESSION_KEY] = historial[-ASSISTANT_HISTORY_LIMIT:]
            request.session.modified = True
        except GeminiSdkError as exc:
            messages.error(request, str(exc))
    return render(
        request,
        'assistant/home.html',
        {
            'form': form,
            'respuesta': respuesta,
            'historial': historial[-ASSISTANT_HISTORY_LIMIT:],
        },
    )
