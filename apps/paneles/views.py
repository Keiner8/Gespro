"""Dashboards renderizados por servidor.

Se usa Chart.js solo para los graficos.
Todo el CRUD debe vivir del lado Django.
"""

from urllib.parse import urlencode

from django.db import DatabaseError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.cuentas.models import Notificacion, Usuario
from apps.cuentas.services import build_dashboard_name
from apps.cuentas.views import get_current_user, login_required, role_required
from apps.academico.models import Aprendiz, AprendizGaes, Ficha, Gaes, Instructor, Trimestre
from apps.proyectos.models import Entregable, Evaluacion, Proyecto

from .reports import REPORT_LABELS, build_rows, excel_response, pdf_response


def ping(request: HttpRequest) -> HttpResponse:
    return HttpResponse('pong')


def _role_name(usuario) -> str:
    return usuario.rol.nombre_rol.lower() if usuario and usuario.rol else ''


def _instructor_ficha_ids(usuario) -> list[int]:
    if _role_name(usuario) != 'instructor':
        return []
    return list(
        Instructor.objects.filter(usuario=usuario, ficha__isnull=False)
        .values_list('ficha_id', flat=True)
        .distinct()
    )


def _aprendiz_profile(usuario):
    if _role_name(usuario) != 'aprendiz':
        return None
    return Aprendiz.objects.filter(usuario=usuario).first()


def _aprendiz_gaes_ids(usuario) -> list[int]:
    aprendiz = _aprendiz_profile(usuario)
    if not aprendiz:
        return []
    return list(AprendizGaes.objects.filter(aprendiz=aprendiz).values_list('gaes_id', flat=True))


def _instructores_count_by_ficha(ficha_id: int | None) -> int:
    if not ficha_id:
        return 0
    try:
        return Instructor.objects.filter(ficha_id=ficha_id, usuario__rol__nombre_rol__iexact='instructor').count()
    except DatabaseError:
        return 0


def _project_status_counts(queryset) -> dict[str, int]:
    return {
        'en_proceso': queryset.filter(estado=Proyecto.Estado.EN_PROCESO).count(),
        'finalizado': queryset.filter(estado=Proyecto.Estado.FINALIZADO).count(),
        'cancelado': queryset.filter(estado=Proyecto.Estado.CANCELADO).count(),
    }


def _trimestre_status_counts(queryset) -> dict[str, int]:
    return {
        'activo': queryset.filter(estado=Trimestre.Estado.ACTIVO).count(),
        'finalizado': queryset.filter(estado=Trimestre.Estado.FINALIZADO).count(),
        'pendiente': queryset.filter(estado=Trimestre.Estado.PENDIENTE).count(),
    }


def _evaluation_range_counts(queryset) -> dict[str, int]:
    return {
        'alto': queryset.filter(calificacion__gte=80).count(),
        'medio': queryset.filter(calificacion__gte=60, calificacion__lt=80).count(),
        'bajo': queryset.filter(calificacion__lt=60).count(),
    }


@login_required
def home(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    rol_nombre = usuario.rol.nombre_rol.lower() if usuario.rol else 'aprendiz'
    return redirect('dashboards:panel', role=rol_nombre)


@login_required
def panel(request: HttpRequest, role: str) -> HttpResponse:
    usuario = get_current_user(request)
    expected_role = build_dashboard_name(usuario)
    if role != expected_role:
        return redirect('dashboards:panel', role=expected_role)

    if expected_role == 'administrador':
        proyectos_qs = Proyecto.objects.all()
        trimestres_qs = Trimestre.objects.all()
        evaluaciones_qs = Evaluacion.objects.all()
        usuarios_qs = Usuario.objects.all()
        role_counts = {
            'administradores': usuarios_qs.filter(rol__nombre_rol__iexact='administrador').count(),
            'instructores': usuarios_qs.filter(rol__nombre_rol__iexact='instructor').count(),
            'aprendices': usuarios_qs.filter(rol__nombre_rol__iexact='aprendiz').count(),
        }
        project_counts = _project_status_counts(proyectos_qs)
        trimestre_counts = _trimestre_status_counts(trimestres_qs)
        evaluation_counts = _evaluation_range_counts(evaluaciones_qs)
        context = {
            'usuario': usuario,
            'total_usuarios': usuarios_qs.count(),
            'total_fichas': Ficha.objects.count(),
            'total_trimestres': trimestres_qs.count(),
            'total_proyectos': proyectos_qs.count(),
            'total_entregables': Entregable.objects.count(),
            'total_evaluaciones': evaluaciones_qs.count(),
            'total_aprendices': Aprendiz.objects.filter(usuario__rol__nombre_rol__iexact='aprendiz').count(),
            'total_instructores': Instructor.objects.filter(usuario__rol__nombre_rol__iexact='instructor').count(),
            'total_gaes': Gaes.objects.count(),
            'usuarios_activos': usuarios_qs.filter(estado=Usuario.Estado.ACTIVO).count(),
            'usuarios_inactivos': usuarios_qs.filter(estado=Usuario.Estado.INACTIVO).count(),
            'project_counts': project_counts,
            'trimestre_counts': trimestre_counts,
            'role_counts': role_counts,
            'evaluation_counts': evaluation_counts,
            'admin_highlight': max(role_counts, key=role_counts.get) if any(role_counts.values()) else 'sin datos',
        }
    elif expected_role == 'instructor':
        ficha_ids = _instructor_ficha_ids(usuario)
        proyectos_qs = Proyecto.objects.filter(gaes__ficha_id__in=ficha_ids).distinct()
        entregables_qs = Entregable.objects.filter(proyecto__gaes__ficha_id__in=ficha_ids).distinct()
        evaluaciones_qs = Evaluacion.objects.filter(entregable__proyecto__gaes__ficha_id__in=ficha_ids).distinct()
        trimestres_qs = Trimestre.objects.filter(ficha_id__in=ficha_ids).distinct()
        project_counts = _project_status_counts(proyectos_qs)
        trimestre_counts = _trimestre_status_counts(trimestres_qs)
        evaluation_counts = _evaluation_range_counts(evaluaciones_qs)
        context = {
            'usuario': usuario,
            'total_usuarios': 0,
            'total_fichas': Ficha.objects.filter(id__in=ficha_ids).count(),
            'total_proyectos': proyectos_qs.count(),
            'total_entregables': entregables_qs.count(),
            'total_evaluaciones': evaluaciones_qs.count(),
            'total_aprendices': Aprendiz.objects.filter(
                ficha_id__in=ficha_ids,
                usuario__rol__nombre_rol__iexact='aprendiz',
            ).distinct().count(),
            'total_instructores': Instructor.objects.filter(
                ficha_id__in=ficha_ids,
                usuario__rol__nombre_rol__iexact='instructor',
            ).distinct().count(),
            'total_gaes': Gaes.objects.filter(ficha_id__in=ficha_ids).distinct().count(),
            'project_counts': project_counts,
            'trimestre_counts': trimestre_counts,
            'evaluation_counts': evaluation_counts,
            'entregables_con_archivo': entregables_qs.filter(Q(archivo__isnull=False) | Q(url__isnull=False)).count(),
            'entregables_sin_soporte': entregables_qs.filter(archivo__isnull=True, url__isnull=True).count(),
            'notificaciones_pendientes': Notificacion.objects.filter(usuario=usuario, leida=False).count(),
        }
    else:
        aprendiz = _aprendiz_profile(usuario)
        gaes_ids = _aprendiz_gaes_ids(usuario)
        proyectos_qs = Proyecto.objects.filter(gaes_id__in=gaes_ids).distinct()
        entregables_qs = Entregable.objects.filter(aprendiz=aprendiz)
        evaluaciones_qs = Evaluacion.objects.filter(Q(aprendiz=aprendiz) | Q(entregable__aprendiz=aprendiz)).distinct()
        project_counts = _project_status_counts(proyectos_qs)
        evaluation_counts = _evaluation_range_counts(evaluaciones_qs)
        context = {
            'usuario': usuario,
            'total_usuarios': 0,
            'total_fichas': 1 if aprendiz and aprendiz.ficha_id else 0,
            'total_proyectos': proyectos_qs.count(),
            'total_entregables': entregables_qs.count(),
            'total_evaluaciones': evaluaciones_qs.count(),
            'total_aprendices': 1 if aprendiz else 0,
            'total_instructores': _instructores_count_by_ficha(aprendiz.ficha_id if aprendiz else None),
            'project_counts': project_counts,
            'evaluation_counts': evaluation_counts,
            'entregables_con_archivo': entregables_qs.filter(Q(archivo__isnull=False) | Q(url__isnull=False)).count(),
            'entregables_sin_soporte': entregables_qs.filter(archivo__isnull=True, url__isnull=True).count(),
            'notificaciones_pendientes': Notificacion.objects.filter(usuario=usuario, leida=False).count(),
            'total_gaes': len(gaes_ids),
        }

    return render(request, f'dashboards/{role}_panel.html', context)


@login_required
@role_required('administrador')
def reportes_home(request: HttpRequest) -> HttpResponse:
    report_name = request.GET.get('tipo') or 'usuarios'
    if report_name not in REPORT_LABELS:
        report_name = 'usuarios'
    filters = {
        'q': request.GET.get('q', '').strip(),
        'rol': request.GET.get('rol', '').strip(),
        'estado': request.GET.get('estado', '').strip(),
        'ficha': request.GET.get('ficha', '').strip(),
    }
    headers, rows = build_rows(report_name, filters)
    export_query = urlencode({key: value for key, value in filters.items() if value})
    context = {
        'report_name': report_name,
        'report_label': REPORT_LABELS.get(report_name, 'Usuarios'),
        'filters': filters,
        'export_query': export_query,
        'headers': headers,
        'rows': rows,
        'generated_at': timezone.localtime(),
        'role_options': ['administrador', 'instructor', 'aprendiz'],
        'user_state_options': Usuario.Estado.choices,
        'ficha_state_options': Ficha.Estado.choices,
        'trimestre_state_options': Trimestre.Estado.choices,
        'ficha_options': Ficha.objects.order_by('codigo_ficha'),
    }
    return render(request, 'dashboards/reportes_home.html', context)


@login_required
@role_required('administrador')
def reportes_export_excel(request: HttpRequest, report_name: str) -> HttpResponse:
    if report_name not in REPORT_LABELS:
        report_name = 'usuarios'
    headers, rows = build_rows(report_name, request.GET)
    report_label = REPORT_LABELS.get(report_name, 'Usuarios')
    return excel_response(f'{report_name}.xlsx', report_label, headers, rows)


@login_required
@role_required('administrador')
def reportes_export_pdf(request: HttpRequest, report_name: str) -> HttpResponse:
    if report_name not in REPORT_LABELS:
        report_name = 'usuarios'
    headers, rows = build_rows(report_name, request.GET)
    report_label = REPORT_LABELS.get(report_name, 'Usuarios')
    return pdf_response(f'{report_name}.pdf', report_label, headers, rows)
