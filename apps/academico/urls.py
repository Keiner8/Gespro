"""Rutas del modulo academico."""

from django.urls import path

from . import views

app_name = 'academic'

urlpatterns = [
    path('fichas/', views.ficha_list, name='ficha_list'),
    path('fichas/nueva/', views.ficha_create, name='ficha_create'),
    path('fichas/<int:pk>/editar/', views.ficha_update, name='ficha_update'),
    path('fichas/<int:pk>/eliminar/', views.ficha_delete, name='ficha_delete'),
    path('trimestres/', views.trimestre_list, name='trimestre_list'),
    path('trimestres/nuevo/', views.trimestre_create, name='trimestre_create'),
    path('trimestres/<int:pk>/editar/', views.trimestre_update, name='trimestre_update'),
    path('trimestres/<int:pk>/eliminar/', views.trimestre_delete, name='trimestre_delete'),
    path('equipos/', views.gaes_list, name='gaes_list'),
    path('equipos/nuevo/', views.gaes_create, name='gaes_create'),
    path('equipos/<int:pk>/editar/', views.gaes_update, name='gaes_update'),
    path('equipos/<int:pk>/eliminar/', views.gaes_delete, name='gaes_delete'),
    path('aprendices/', views.aprendiz_list, name='aprendiz_list'),
    path('aprendices/nuevo/', views.aprendiz_create, name='aprendiz_create'),
    path('aprendices/carga-masiva/', views.aprendices_bulk_upload, name='aprendiz_bulk_upload'),
    path('aprendices/<int:pk>/editar/', views.aprendiz_update, name='aprendiz_update'),
    path('aprendices/<int:pk>/eliminar/', views.aprendiz_delete, name='aprendiz_delete'),
    path('instructores/', views.instructor_list, name='instructor_list'),
    path('instructores/nuevo/', views.instructor_create, name='instructor_create'),
    path('instructores/carga-masiva/', views.instructores_bulk_upload, name='instructor_bulk_upload'),
    path('instructores/<int:pk>/editar/', views.instructor_update, name='instructor_update'),
    path('instructores/<int:pk>/eliminar/', views.instructor_delete, name='instructor_delete'),
]
