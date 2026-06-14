"""Servicios del modulo academico."""

import calendar
from datetime import date, timedelta

from django.utils import timezone

from .models import Aprendiz, AprendizGaes, Ficha, Trimestre


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def trimestre_date_range(ficha: Ficha, numero: int) -> tuple[date, date]:
    fecha_inicio = _add_months(ficha.fecha_inicio, (numero - 1) * 3)
    fecha_fin = _add_months(fecha_inicio, 3) - timedelta(days=1)
    return fecha_inicio, fecha_fin


def trimestre_estado_para_fechas(fecha_inicio: date, fecha_fin: date) -> str:
    hoy = timezone.localdate()
    if fecha_fin < hoy:
        return Trimestre.Estado.FINALIZADO
    if fecha_inicio > hoy:
        return Trimestre.Estado.PENDIENTE
    return Trimestre.Estado.ACTIVO


def sync_trimestres_for_ficha(ficha: Ficha) -> None:
    """Completa los periodos esperados sin sobrescribir registros existentes."""
    total = 7 if ficha.nivel == Ficha.Nivel.TECNOLOGO else 4
    for numero in range(1, total + 1):
        fecha_inicio, fecha_fin = trimestre_date_range(ficha, numero)
        Trimestre.objects.get_or_create(
            ficha=ficha,
            numero=numero,
            defaults={
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'estado': trimestre_estado_para_fechas(fecha_inicio, fecha_fin),
            },
        )


def validate_aprendiz_en_ficha(usuario, ficha, exclude_aprendiz_id=None):
    """Evita duplicar el mismo aprendiz dentro de una misma ficha."""
    if not usuario or not ficha:
        return None

    queryset = Aprendiz.objects.select_related('usuario', 'usuario__rol', 'ficha').filter(
        ficha=ficha,
        usuario__rol__nombre_rol__iexact='aprendiz',
    )
    if exclude_aprendiz_id is not None:
        queryset = queryset.exclude(id=exclude_aprendiz_id)

    if queryset.filter(usuario=usuario).exists():
        return 'Este aprendiz ya esta registrado en esa ficha.'

    if queryset.filter(usuario__numero_documento=usuario.numero_documento).exists():
        return 'Ya existe un aprendiz con ese documento en esa ficha.'

    return None


def sync_aprendiz_gaes(aprendiz, gaes):
    """Mantiene la asignacion Scrum del aprendiz desde el formulario server-side."""
    AprendizGaes.objects.filter(aprendiz=aprendiz).delete()
    if gaes:
        AprendizGaes.objects.get_or_create(aprendiz=aprendiz, gaes=gaes)


def ficha_cupos_disponibles(ficha: Ficha) -> int:
    total = Aprendiz.objects.filter(ficha=ficha, usuario__rol__nombre_rol__iexact='aprendiz').count()
    return max(30 - total, 0)
