"""Rutas principales del nuevo GESPRO Django puro."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from apps.paneles.views import ping

urlpatterns = [
    path('admin/', admin.site.urls),
    path('ping/', ping, name='ping'),
    path('', include('apps.cuentas.urls')),
    path('dashboard/', include('apps.paneles.urls')),
    path('academic/', include('apps.academico.urls')),
    path('projects/', include('apps.proyectos.urls')),
    path('assistant/', include('apps.asistente.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
