from django.contrib import admin

from .models import Entregable, Evaluacion, Proyecto, ProyectoEntregable

admin.site.register(Proyecto)
admin.site.register(Entregable)
admin.site.register(ProyectoEntregable)
admin.site.register(Evaluacion)
