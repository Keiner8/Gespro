from django.contrib import admin

from .models import Aprendiz, AprendizGaes, Ficha, Gaes, Instructor, Trimestre

admin.site.register(Ficha)
admin.site.register(Aprendiz)
admin.site.register(Instructor)
admin.site.register(Trimestre)
admin.site.register(Gaes)
admin.site.register(AprendizGaes)
