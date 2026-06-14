"""Carga datos maestros necesarios para iniciar GESPRO."""

from django.core.management.base import BaseCommand

from apps.cuentas.models import Rol, Usuario
from apps.cuentas.services import create_profile_for_role, ensure_default_ficha, ensure_default_roles


class Command(BaseCommand):
    help = 'Crea o actualiza los datos maestros iniciales de GESPRO.'

    def handle(self, *args, **options):
        ensure_default_roles()
        ficha = ensure_default_ficha()
        usuarios_count = 0
        for usuario in Usuario.objects.select_related('rol').all():
            create_profile_for_role(usuario)
            usuarios_count += 1
        roles = ', '.join(Rol.objects.order_by('id').values_list('nombre_rol', flat=True))
        self.stdout.write(self.style.SUCCESS(f'Datos iniciales cargados correctamente. Roles: {roles}'))
        self.stdout.write(self.style.SUCCESS(f'Ficha inicial disponible: {ficha.codigo_ficha}'))
        self.stdout.write(self.style.SUCCESS(f'Perfiles de usuario verificados: {usuarios_count}'))
