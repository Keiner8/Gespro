"""Vistas del asistente virtual renderizadas por servidor."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.cuentas.views import login_required, role_required

from .forms import AssistantPromptForm
from .services import GeminiSdkError, generar_respuesta_gemini


@login_required
@role_required('administrador')
def assistant_home(request: HttpRequest) -> HttpResponse:
    respuesta = ''
    form = AssistantPromptForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            respuesta = generar_respuesta_gemini(form.cleaned_data['texto'])
        except GeminiSdkError as exc:
            messages.error(request, str(exc))
    return render(request, 'assistant/home.html', {'form': form, 'respuesta': respuesta})
