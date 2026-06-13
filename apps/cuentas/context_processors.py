"""Contexto global para navegacion por rol."""

from .models import Notificacion, Usuario


def current_usuario(request):
    user_id = request.session.get('gespro_user_id')
    usuario = None
    recent_notifications = []
    unread_notifications_count = 0
    resolver_match = getattr(request, 'resolver_match', None)
    if user_id:
        usuario = Usuario.objects.select_related('rol').filter(id=user_id).first()
        if usuario and usuario.estado != Usuario.Estado.ACTIVO:
            request.session.flush()
            usuario = None
        if usuario:
            notifications_qs = Notificacion.objects.filter(usuario=usuario)
            recent_notifications = list(notifications_qs[:5])
            unread_notifications_count = notifications_qs.filter(leida=False).count()
    return {
        'current_usuario': usuario,
        'recent_notifications': recent_notifications,
        'unread_notifications_count': unread_notifications_count,
        'current_path': request.path,
        'current_namespace': resolver_match.namespace if resolver_match else '',
        'current_url_name': resolver_match.url_name if resolver_match else '',
        'current_query': request.GET.get('q', '').strip(),
    }
