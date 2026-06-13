"""Rutas del modulo de cuentas."""

from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('perfil/', views.profile_view, name='profile'),
    path('notificaciones/', views.notificaciones_list, name='notificaciones_list'),
    path('notificaciones/<int:pk>/leer/', views.notificacion_marcar_leida, name='notificacion_mark_read'),
    path('notificaciones/<int:pk>/eliminar/', views.notificacion_eliminar, name='notificacion_delete'),
    path('notificaciones/marcar-todas/', views.notificaciones_marcar_todas, name='notificaciones_mark_all'),
    path('password-recovery/', views.password_recovery_request, name='password_recovery'),
    path('password-reset-confirm/', views.password_reset_confirm, name='password_reset_confirm'),
    path('usuarios/', views.usuarios_list, name='usuarios_list'),
    path('usuarios/nuevo/', views.usuarios_create, name='usuarios_create'),
    path('usuarios/<int:pk>/editar/', views.usuarios_update, name='usuarios_update'),
    path('usuarios/<int:pk>/toggle-estado/', views.usuarios_toggle_estado, name='usuarios_toggle_estado'),
]
