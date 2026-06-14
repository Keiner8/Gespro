"""Vistas para entregar archivos multimedia privados del sistema."""

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest

from .models import Usuario


def media_file(request: HttpRequest, path: str) -> FileResponse:
    user_id = request.session.get('gespro_user_id')
    if not user_id or not Usuario.objects.filter(id=user_id, estado=Usuario.Estado.ACTIVO).exists():
        raise Http404()

    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested_path = (media_root / path).resolve()
    if not requested_path.is_file() or not requested_path.is_relative_to(media_root):
        raise Http404()

    return FileResponse(requested_path.open('rb'))
