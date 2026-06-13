"""Carga datos maestros necesarios para iniciar GESPRO."""

from django.core.management.base import BaseCommand

from apps.cuentas.models import Rol
from apps.cuentas.services import ensure_default_roles


class Command(BaseCommand):
    help = 'Crea o actualiza los datos maestros iniciales de GESPRO.'

    def handle(self, *args, **options):
        ensure_default_roles()
        roles = ', '.join(Rol.objects.order_by('id').values_list('nombre_rol', flat=True))
        self.stdout.write(self.style.SUCCESS(f'Datos iniciales cargados correctamente. Roles: {roles}'))
