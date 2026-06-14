"""Carga datos maestros necesarios para iniciar GESPRO."""

from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import check_password

from apps.cuentas.models import Rol, Usuario
from apps.cuentas.services import create_profile_for_role, ensure_default_ficha, ensure_default_roles


class Command(BaseCommand):
    help = 'Crea o actualiza los datos maestros iniciales de GESPRO.'

    def handle(self, *args, **options):
        ensure_default_roles()
        ficha = ensure_default_ficha()
        usuarios_count = 0
        temporales_count = 0
        for usuario in Usuario.objects.select_related('rol').all():
            create_profile_for_role(usuario)
            if check_password('Temporal123*', usuario.password):
                usuario.debe_cambiar_password = True
                usuario.password_temporal = True
                usuario.save(update_fields=['debe_cambiar_password', 'password_temporal'])
                temporales_count += 1
            usuarios_count += 1
        roles = ', '.join(Rol.objects.order_by('id').values_list('nombre_rol', flat=True))
        self.stdout.write(self.style.SUCCESS(f'Datos iniciales cargados correctamente. Roles: {roles}'))
        self.stdout.write(self.style.SUCCESS(f'Ficha inicial disponible: {ficha.codigo_ficha}'))
        self.stdout.write(self.style.SUCCESS(f'Perfiles de usuario verificados: {usuarios_count}'))
        self.stdout.write(self.style.SUCCESS(f'Cuentas temporales marcadas para cambio de contrasena: {temporales_count}'))
