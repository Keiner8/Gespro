"""Rutas del modulo de proyectos."""

from django.urls import path

from . import views

app_name = 'projects'

urlpatterns = [
    path('proyectos/', views.proyecto_list, name='proyecto_list'),
    path('proyectos/nuevo/', views.proyecto_create, name='proyecto_create'),
    path('proyectos/<int:pk>/editar/', views.proyecto_update, name='proyecto_update'),
    path('proyectos/<int:pk>/eliminar/', views.proyecto_delete, name='proyecto_delete'),
    path('entregables/', views.entregable_list, name='entregable_list'),
    path('entregables/nuevo/', views.entregable_create, name='entregable_create'),
    path('entregables/<int:pk>/abrir/', views.entregable_open, name='entregable_open'),
    path('entregables/<int:pk>/vista/', views.entregable_inline, name='entregable_inline'),
    path('entregables/<int:pk>/descargar/', views.entregable_download, name='entregable_download'),
    path('entregables/<int:pk>/editar/', views.entregable_update, name='entregable_update'),
    path('entregables/<int:pk>/eliminar/', views.entregable_delete, name='entregable_delete'),
    path('historial-trimestres/', views.historial_trimestres, name='historial_trimestres'),
    path('evaluaciones/', views.evaluacion_list, name='evaluacion_list'),
    path('evaluaciones/nueva/', views.evaluacion_create, name='evaluacion_create'),
    path('evaluaciones/<int:pk>/editar/', views.evaluacion_update, name='evaluacion_update'),
    path('evaluaciones/<int:pk>/eliminar/', views.evaluacion_delete, name='evaluacion_delete'),
    path('evaluacion-final/', views.evaluacion_final_list, name='evaluacion_final_list'),
    path('evaluacion-final/<int:aprendiz_id>/<int:trimestre_id>/<str:estado>/', views.evaluacion_final_guardar, name='evaluacion_final_guardar'),
    path('evaluacion-final/reporte/excel/', views.evaluacion_final_excel, name='evaluacion_final_excel'),
    path('evaluacion-final/reporte/pdf/', views.evaluacion_final_pdf, name='evaluacion_final_pdf'),
]
