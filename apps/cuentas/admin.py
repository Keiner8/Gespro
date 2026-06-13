from django.contrib import admin

from .models import Administrador, Notificacion, Rol, Usuario

admin.site.register(Rol)
admin.site.register(Usuario)
admin.site.register(Administrador)
admin.site.register(Notificacion)
