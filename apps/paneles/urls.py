"""Rutas de dashboards por rol."""

from django.urls import path

from . import views

app_name = 'dashboards'

urlpatterns = [
    path('', views.home, name='home'),
    path('reportes/', views.reportes_home, name='reportes_home'),
    path('reportes/<str:report_name>/excel/', views.reportes_export_excel, name='reportes_export_excel'),
    path('reportes/<str:report_name>/pdf/', views.reportes_export_pdf, name='reportes_export_pdf'),
    path('<str:role>/', views.panel, name='panel'),
]
