"""CRUD server-side del dominio de proyectos."""

import mimetypes
from pathlib import Path
from io import BytesIO

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import content_disposition_header
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.cuentas.models import Notificacion
from apps.cuentas.views import get_current_user, login_required, role_required
from apps.academico.models import Aprendiz, AprendizGaes, Ficha, Gaes, Instructor, Trimestre
from apps.paneles.reports import pdf_response

from .forms import EntregaEvidenciaForm, EntregableForm, EvaluacionForm, ProyectoForm
from .models import Entregable, Evaluacion, EvaluacionFinalTrimestre, Proyecto


TEXT_PREVIEW_TYPES = {
    'text/plain',
    'text/csv',
    'application/json',
    'application/xml',
    'text/xml',
}


def _role_name(usuario) -> str:
    return usuario.rol.nombre_rol.lower() if usuario and usuario.rol else ''


def _usuario_label(usuario) -> str:
    nombre = str(usuario).strip()
    return nombre or getattr(usuario, 'correo', '') or f'usuario #{usuario.id}'


def _aprendiz_label(aprendiz) -> str:
    return _usuario_label(aprendiz.usuario) if aprendiz else 'aprendiz sin asignar'


def _gaes_label(gaes) -> str:
    return gaes.nombre if gaes else 'equipo sin asignar'


def _ficha_label(ficha) -> str:
    return ficha.codigo_ficha if ficha else 'sin ficha'


def _proyecto_label(proyecto) -> str:
    return proyecto.nombre if proyecto else 'proyecto sin nombre'


def _entregable_destino_label(entregable) -> str:
    if entregable.aprendiz_id:
        return f'a {_aprendiz_label(entregable.aprendiz)}'
    if entregable.proyecto_id and entregable.proyecto and entregable.proyecto.gaes:
        return f'al equipo Scrum {_gaes_label(entregable.proyecto.gaes)}'
    return 'al equipo asignado'


def _evaluacion_destino_label(evaluacion) -> str:
    if evaluacion.aprendiz_id:
        return _aprendiz_label(evaluacion.aprendiz)
    if evaluacion.gaes_id:
        return f'equipo Scrum {_gaes_label(evaluacion.gaes)}'
    return 'destinatario asignado'


def _get_aprendiz_profile(usuario):
    if _role_name(usuario) != 'aprendiz':
        return None
    return Aprendiz.objects.filter(usuario=usuario).first()


def _get_instructor_profiles(usuario):
    if _role_name(usuario) != 'instructor':
        return Instructor.objects.none()
    return Instructor.objects.filter(usuario=usuario).select_related('ficha', 'trimestre', 'usuario')


def _get_current_instructor_for_evaluation(usuario, ficha_id=None):
    instructores = _get_instructor_profiles(usuario)
    if ficha_id:
        instructor = instructores.filter(ficha_id=ficha_id).first()
        if instructor:
            return instructor
    return instructores.exclude(ficha__isnull=True).first() or instructores.first()


def _get_instructor_ficha_ids(usuario) -> list[int]:
    if _role_name(usuario) != 'instructor':
        return []
    return list(_get_instructor_profiles(usuario).exclude(ficha__isnull=True).values_list('ficha_id', flat=True).distinct())


def _get_instructor_trimestre_ids(usuario) -> list[int]:
    if _role_name(usuario) != 'instructor':
        return []
    return list(_get_instructor_profiles(usuario).exclude(trimestre__isnull=True).values_list('trimestre_id', flat=True).distinct())


def _get_aprendiz_gaes_ids(aprendiz) -> list[int]:
    if not aprendiz:
        return []
    return list(AprendizGaes.objects.filter(aprendiz=aprendiz).values_list('gaes_id', flat=True))


def _clean_filter_id(value):
    return int(value) if value and str(value).isdigit() else None


def _search_query(request: HttpRequest) -> str:
    return request.GET.get('q', '').strip()


def _filter_proyectos(queryset, query: str):
    if not query:
        return queryset
    return queryset.filter(
        Q(nombre__icontains=query)
        | Q(descripcion__icontains=query)
        | Q(estado__icontains=query)
        | Q(gaes__nombre__icontains=query)
        | Q(gaes__ficha__codigo_ficha__icontains=query)
        | Q(gaes__ficha__programa_formacion__icontains=query)
    ).distinct()


def _filter_entregables(queryset, query: str):
    if not query:
        return queryset
    filters = (
        Q(nombre__icontains=query)
        | Q(descripcion__icontains=query)
        | Q(proyecto__nombre__icontains=query)
        | Q(proyecto__gaes__nombre__icontains=query)
        | Q(proyecto__gaes__ficha__codigo_ficha__icontains=query)
        | Q(aprendiz__usuario__nombre__icontains=query)
        | Q(aprendiz__usuario__apellido__icontains=query)
        | Q(nombre_archivo__icontains=query)
        | Q(url__icontains=query)
    )
    if query.isdigit():
        filters |= Q(trimestre__numero=int(query))
    return queryset.filter(filters).distinct()


def _filter_evaluaciones(queryset, query: str):
    if not query:
        return queryset
    filters = (
        Q(entregable__nombre__icontains=query)
        | Q(aprendiz__usuario__nombre__icontains=query)
        | Q(aprendiz__usuario__apellido__icontains=query)
        | Q(entregable__aprendiz__usuario__nombre__icontains=query)
        | Q(entregable__aprendiz__usuario__apellido__icontains=query)
        | Q(gaes__nombre__icontains=query)
        | Q(evaluador__usuario__nombre__icontains=query)
        | Q(evaluador__usuario__apellido__icontains=query)
        | Q(observaciones__icontains=query)
    )
    return queryset.filter(filters).distinct()


def _entregable_vencido(entregable: Entregable) -> bool:
    return bool(entregable.fecha_limite and timezone.localdate() > entregable.fecha_limite)


def _fichas_queryset_for_user(usuario):
    queryset = Ficha.objects.all()
    if _role_name(usuario) == 'instructor':
        queryset = queryset.filter(id__in=_get_instructor_ficha_ids(usuario))
    return queryset.order_by('codigo_ficha').distinct()


def _proyectos_queryset(usuario):
    queryset = Proyecto.objects.select_related('gaes', 'gaes__ficha').all()
    rol = _role_name(usuario)
    if rol == 'instructor':
        queryset = queryset.filter(gaes__ficha_id__in=_get_instructor_ficha_ids(usuario))
    elif rol == 'aprendiz':
        queryset = queryset.filter(gaes_id__in=_get_aprendiz_gaes_ids(_get_aprendiz_profile(usuario)))
    return queryset.distinct()


def _entregables_queryset(usuario):
    queryset = Entregable.objects.select_related('proyecto', 'trimestre', 'aprendiz__usuario').all()
    rol = _role_name(usuario)
    if rol == 'instructor':
        queryset = queryset.filter(
            proyecto__gaes__ficha_id__in=_get_instructor_ficha_ids(usuario),
            trimestre_id__in=_get_instructor_trimestre_ids(usuario),
        )
    elif rol == 'aprendiz':
        aprendiz = _get_aprendiz_profile(usuario)
        gaes_ids = _get_aprendiz_gaes_ids(aprendiz)
        queryset = queryset.filter(Q(aprendiz=aprendiz) | Q(aprendiz__isnull=True, proyecto__gaes_id__in=gaes_ids))
    return queryset.distinct()


def _evaluaciones_queryset(usuario):
    queryset = Evaluacion.objects.select_related(
        'entregable',
        'entregable__aprendiz',
        'entregable__aprendiz__usuario',
        'aprendiz__usuario',
        'evaluador__usuario',
        'gaes',
    ).all()
    rol = _role_name(usuario)
    if rol == 'instructor':
        queryset = queryset.filter(
            entregable__proyecto__gaes__ficha_id__in=_get_instructor_ficha_ids(usuario),
            entregable__trimestre_id__in=_get_instructor_trimestre_ids(usuario),
        )
    elif rol == 'aprendiz':
        aprendiz = _get_aprendiz_profile(usuario)
        gaes_ids = _get_aprendiz_gaes_ids(aprendiz)
        queryset = queryset.filter(Q(aprendiz=aprendiz) | Q(entregable__aprendiz=aprendiz) | Q(gaes_id__in=gaes_ids))
    return queryset.distinct()


def _gaes_queryset_for_user(usuario):
    rol = _role_name(usuario)
    queryset = Gaes.objects.select_related('ficha').all()
    if rol == 'instructor':
        queryset = queryset.filter(ficha_id__in=_get_instructor_ficha_ids(usuario))
    elif rol == 'aprendiz':
        queryset = queryset.filter(id__in=_get_aprendiz_gaes_ids(_get_aprendiz_profile(usuario)))
    return queryset.distinct()


def _trimestres_queryset_for_user(usuario):
    rol = _role_name(usuario)
    queryset = Trimestre.objects.select_related('ficha').all()
    if rol == 'instructor':
        queryset = queryset.filter(id__in=_get_instructor_trimestre_ids(usuario))
    elif rol == 'aprendiz':
        queryset = queryset.filter(ficha__gaes__id__in=_get_aprendiz_gaes_ids(_get_aprendiz_profile(usuario)))
    return queryset.distinct()


def _aprendices_queryset_for_user(usuario):
    rol = _role_name(usuario)
    queryset = Aprendiz.objects.select_related('usuario', 'usuario__rol', 'ficha').filter(
        usuario__rol__nombre_rol__iexact='aprendiz',
    )
    if rol == 'instructor':
        queryset = queryset.filter(ficha_id__in=_get_instructor_ficha_ids(usuario))
    elif rol == 'aprendiz':
        queryset = queryset.filter(usuario=usuario)
    return queryset.distinct()


def _apply_proyecto_form_permissions(form, usuario):
    form.fields['gaes'].queryset = _gaes_queryset_for_user(usuario)


def _apply_entregable_form_permissions(form, usuario, ficha_id=None, gaes_id=None, destino='scrum'):
    proyectos = _proyectos_queryset(usuario)
    trimestres = _trimestres_queryset_for_user(usuario)
    aprendices = _aprendices_queryset_for_user(usuario)

    if ficha_id:
        proyectos = proyectos.filter(gaes__ficha_id=ficha_id)
        trimestres = trimestres.filter(ficha_id=ficha_id)
        aprendices = aprendices.filter(ficha_id=ficha_id)
    elif _role_name(usuario) in {'administrador', 'instructor'}:
        proyectos = proyectos.none()
        trimestres = trimestres.none()
        aprendices = aprendices.none()

    if gaes_id:
        proyectos = proyectos.filter(gaes_id=gaes_id)
        aprendices = aprendices.filter(gaes_links__gaes_id=gaes_id)

    form.fields['proyecto'].queryset = proyectos.distinct()
    form.fields['trimestre'].queryset = trimestres.distinct()
    form.fields['aprendiz'].queryset = aprendices.distinct() if destino == 'aprendiz' else aprendices.none()
    if _role_name(usuario) == 'aprendiz':
        aprendiz = _get_aprendiz_profile(usuario)
        form.fields['aprendiz'].initial = aprendiz


def _entregable_filter_context(usuario, ficha_id=None, gaes_id=None, destino='scrum'):
    fichas = _fichas_queryset_for_user(usuario)
    equipos = _gaes_queryset_for_user(usuario)
    if ficha_id:
        equipos = equipos.filter(ficha_id=ficha_id)
    equipo_seleccionado = equipos.filter(id=gaes_id).first() if gaes_id else None
    aprendices_scrum = Aprendiz.objects.none()
    aprendices_disponibles = Aprendiz.objects.none()
    if ficha_id and destino == 'aprendiz':
        aprendices_disponibles = _aprendices_queryset_for_user(usuario).filter(ficha_id=ficha_id)
    if gaes_id:
        aprendices_scrum = Aprendiz.objects.select_related('usuario', 'usuario__rol', 'ficha').filter(
            gaes_links__gaes_id=gaes_id,
            usuario__rol__nombre_rol__iexact='aprendiz',
        ).order_by(
            'usuario__nombre',
            'usuario__apellido',
        )
        if destino == 'aprendiz':
            aprendices_disponibles = aprendices_disponibles.filter(gaes_links__gaes_id=gaes_id)
    return {
        'fichas': fichas,
        'equipos_scrum': equipos.order_by('nombre').distinct(),
        'equipo_seleccionado': equipo_seleccionado,
        'aprendices_scrum': aprendices_scrum,
        'aprendices_disponibles': aprendices_disponibles.order_by('usuario__nombre', 'usuario__apellido').distinct(),
        'selected_ficha_id': ficha_id,
        'selected_gaes_id': gaes_id,
        'selected_destino': destino,
    }


def _apply_evaluacion_form_permissions(form, usuario, ficha_id=None, gaes_id=None):
    entregables = _entregables_queryset(usuario)
    aprendices = _aprendices_queryset_for_user(usuario)
    equipos = _gaes_queryset_for_user(usuario)

    if ficha_id:
        entregables = entregables.filter(proyecto__gaes__ficha_id=ficha_id)
        aprendices = aprendices.filter(ficha_id=ficha_id)
        equipos = equipos.filter(ficha_id=ficha_id)

    if gaes_id:
        entregables = entregables.filter(proyecto__gaes_id=gaes_id)
        aprendices = aprendices.filter(gaes_links__gaes_id=gaes_id)
        equipos = equipos.filter(id=gaes_id)

    form.fields['entregable'].queryset = entregables.distinct()
    form.fields['aprendiz'].queryset = aprendices.distinct()
    form.fields['gaes'].queryset = equipos.distinct()
    if gaes_id and not form.is_bound:
        form.fields['gaes'].initial = gaes_id
    if _role_name(usuario) == 'instructor':
        instructor_actual = _get_current_instructor_for_evaluation(usuario, ficha_id=ficha_id)
        if instructor_actual:
            form.fields['evaluador'].queryset = Instructor.objects.filter(pk=instructor_actual.pk)
            form.fields['evaluador'].initial = instructor_actual
            form.fields['evaluador'].empty_label = None


def _evaluacion_filter_context(usuario, ficha_id=None, gaes_id=None):
    fichas = _fichas_queryset_for_user(usuario)
    equipos = _gaes_queryset_for_user(usuario)
    if ficha_id:
        equipos = equipos.filter(ficha_id=ficha_id)
    equipos = equipos.annotate(total_aprendices=Count('aprendiz_links', distinct=True)).order_by('nombre')

    aprendices_scrum = Aprendiz.objects.none()
    equipo_seleccionado = None
    if gaes_id:
        equipo_seleccionado = equipos.filter(id=gaes_id).first() or _gaes_queryset_for_user(usuario).filter(id=gaes_id).first()
        aprendices_scrum = Aprendiz.objects.select_related('usuario', 'ficha').filter(gaes_links__gaes_id=gaes_id).order_by(
            'usuario__nombre',
            'usuario__apellido',
        )

    return {
        'fichas': fichas,
        'equipos_scrum': equipos,
        'equipo_seleccionado': equipo_seleccionado,
        'aprendices_scrum': aprendices_scrum,
        'selected_ficha_id': ficha_id,
        'selected_gaes_id': gaes_id,
    }


def _crear_notificacion(usuario, titulo: str, mensaje: str, url_destino: str = '', tipo: str = Notificacion.Tipo.INFO):
    if not usuario:
        return
    Notificacion.objects.create(
        usuario=usuario,
        titulo=titulo,
        mensaje=mensaje,
        url_destino=url_destino or '',
        tipo=tipo,
    )


def _notificar_instructores_por_entregable(entregable: Entregable, accion: str):
    ficha_id = entregable.proyecto.gaes.ficha_id if entregable.proyecto and entregable.proyecto.gaes else None
    if not ficha_id:
        return
    instructores = Instructor.objects.select_related('usuario').filter(ficha_id=ficha_id, usuario__estado='activo')
    aprendiz_nombre = ''
    if entregable.aprendiz and entregable.aprendiz.usuario:
        aprendiz_nombre = f'{entregable.aprendiz.usuario.nombre} {entregable.aprendiz.usuario.apellido}'.strip()
    for instructor in instructores:
        _crear_notificacion(
            instructor.usuario,
            titulo=f'Entregable {accion}',
            mensaje=f'Se {accion} el entregable "{entregable.nombre}" del proyecto "{entregable.proyecto.nombre}" por {aprendiz_nombre or "un aprendiz"}.',
            url_destino='/projects/entregables/',
            tipo=Notificacion.Tipo.INFO,
        )


def _notificar_aprendices_por_entregable(entregable: Entregable, accion: str):
    if entregable.aprendiz and entregable.aprendiz.usuario:
        aprendices = [entregable.aprendiz]
    elif entregable.proyecto and entregable.proyecto.gaes_id:
        aprendices = Aprendiz.objects.select_related('usuario').filter(gaes_links__gaes=entregable.proyecto.gaes)
    else:
        aprendices = []

    for aprendiz in aprendices:
        _crear_notificacion(
            aprendiz.usuario,
            titulo=f'Entregable {accion}',
            mensaje=f'Tienes un entregable asignado: "{entregable.nombre}" del proyecto "{entregable.proyecto.nombre}".',
            url_destino='/projects/entregables/',
            tipo=Notificacion.Tipo.INFO,
        )


def _notificar_aprendiz_por_evaluacion(evaluacion: Evaluacion, accion: str):
    aprendices = []
    aprendiz = evaluacion.aprendiz or evaluacion.entregable.aprendiz
    if aprendiz:
        aprendices = [aprendiz]
    elif evaluacion.gaes_id:
        aprendices = list(Aprendiz.objects.select_related('usuario').filter(gaes_links__gaes=evaluacion.gaes).distinct())

    for aprendiz_item in aprendices:
        if not aprendiz_item.usuario:
            continue
        _crear_notificacion(
            aprendiz_item.usuario,
            titulo=f'Evaluacion {accion}',
            mensaje=(
                f'Se {accion} una evaluacion para tu entregable "{evaluacion.entregable.nombre}" '
                f'con calificacion {evaluacion.calificacion} en escala {evaluacion.get_escala_calificacion_display()}.'
            ),
            url_destino='/projects/evaluaciones/',
            tipo=Notificacion.Tipo.EXITO,
        )


def _instructor_assignments(usuario):
    return _get_instructor_profiles(usuario).select_related('ficha', 'trimestre').filter(
        ficha__isnull=False,
        trimestre__isnull=False,
    )


def _evaluacion_final_rows(usuario):
    rows = []
    for instructor in _instructor_assignments(usuario):
        aprendices = Aprendiz.objects.select_related('usuario', 'ficha').filter(ficha=instructor.ficha).order_by(
            'usuario__nombre',
            'usuario__apellido',
        )
        finales = {
            item.aprendiz_id: item
            for item in EvaluacionFinalTrimestre.objects.filter(
                trimestre=instructor.trimestre,
                aprendiz__in=aprendices,
            )
        }
        for aprendiz in aprendices:
            rows.append(
                {
                    'instructor': instructor,
                    'aprendiz': aprendiz,
                    'trimestre': instructor.trimestre,
                    'evaluacion_final': finales.get(aprendiz.id),
                }
            )
    return rows


def _filter_evaluacion_final_rows(rows, selected_estado='', selected_ficha_id=None):
    filtered = rows
    if selected_ficha_id:
        filtered = [row for row in filtered if row['aprendiz'].ficha_id == selected_ficha_id]
    if selected_estado == EvaluacionFinalTrimestre.Estado.APROBADO:
        filtered = [row for row in filtered if row['evaluacion_final'] and row['evaluacion_final'].estado == EvaluacionFinalTrimestre.Estado.APROBADO]
    elif selected_estado == EvaluacionFinalTrimestre.Estado.NO_APROBADO:
        filtered = [row for row in filtered if row['evaluacion_final'] and row['evaluacion_final'].estado == EvaluacionFinalTrimestre.Estado.NO_APROBADO]
    elif selected_estado == 'pendiente':
        filtered = [row for row in filtered if not row['evaluacion_final']]
    return filtered


def _notificar_evaluacion_final(evaluacion_final: EvaluacionFinalTrimestre):
    aprendiz = evaluacion_final.aprendiz
    if not aprendiz or not aprendiz.usuario:
        return
    estado_texto = 'aprobaste' if evaluacion_final.estado == EvaluacionFinalTrimestre.Estado.APROBADO else 'no aprobaste'
    _crear_notificacion(
        aprendiz.usuario,
        titulo='Resultado final del trimestre',
        mensaje=(
            f'{aprendiz.usuario.nombre}, {estado_texto} el trimestre {evaluacion_final.trimestre.numero} '
            f'de la ficha {evaluacion_final.trimestre.ficha.codigo_ficha}.'
        ),
        url_destino='/projects/evaluaciones/',
        tipo=Notificacion.Tipo.EXITO if evaluacion_final.estado == EvaluacionFinalTrimestre.Estado.APROBADO else Notificacion.Tipo.ALERTA,
    )


def _final_report_rows(usuario, selected_estado='', selected_ficha_id=None):
    headers = ['Ficha', 'Trimestre', 'Aprendiz', 'Documento', 'Estado', 'Instructor', 'Fecha']
    rows = []
    for row in _filter_evaluacion_final_rows(_evaluacion_final_rows(usuario), selected_estado, selected_ficha_id):
        final = row['evaluacion_final']
        aprendiz = row['aprendiz']
        instructor = row['instructor']
        rows.append(
            [
                row['trimestre'].ficha.codigo_ficha,
                row['trimestre'].numero,
                f'{aprendiz.usuario.nombre} {aprendiz.usuario.apellido}'.strip(),
                f'{aprendiz.usuario.tipo_documento} {aprendiz.usuario.numero_documento}',
                final.get_estado_display() if final else 'Pendiente',
                f'{instructor.usuario.nombre} {instructor.usuario.apellido}'.strip(),
                timezone.localtime(final.fecha).strftime('%d/%m/%Y') if final else '',
            ]
        )
    return headers, rows


def _historial_trimestral_aprendiz(usuario):
    aprendiz = _get_aprendiz_profile(usuario)
    if not aprendiz or not aprendiz.ficha_id:
        return None, []

    gaes_ids = _get_aprendiz_gaes_ids(aprendiz)
    trimestres = Trimestre.objects.filter(ficha=aprendiz.ficha).order_by('numero')
    rows = []
    for trimestre in trimestres:
        evaluaciones = _evaluaciones_queryset(usuario).filter(entregable__trimestre=trimestre)
        instructores = Instructor.objects.select_related('usuario').filter(
            Q(trimestre=trimestre, ficha=aprendiz.ficha) | Q(evaluaciones_realizadas__in=evaluaciones)
        ).distinct()
        entregables = Entregable.objects.select_related('proyecto').filter(
            trimestre=trimestre,
        ).filter(
            Q(aprendiz=aprendiz) | Q(aprendiz__isnull=True, proyecto__gaes_id__in=gaes_ids)
        ).distinct()
        rows.append(
            {
                'trimestre': trimestre,
                'instructores': instructores,
                'evaluaciones': evaluaciones,
                'entregables': entregables,
                'evaluacion_final': EvaluacionFinalTrimestre.objects.filter(aprendiz=aprendiz, trimestre=trimestre).first(),
            }
        )
    return aprendiz, rows


@login_required
def proyecto_list(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    queryset = _filter_proyectos(_proyectos_queryset(usuario), _search_query(request))
    return render(request, 'projects/proyectos_list.html', {'proyectos': queryset})


@login_required
@role_required('administrador', 'instructor', 'aprendiz')
def proyecto_create(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    form = ProyectoForm(request.POST or None)
    _apply_proyecto_form_permissions(form, usuario)
    if request.method == 'POST' and form.is_valid():
        proyecto = form.save()
        messages.success(request, 'Proyecto creado correctamente.')
        return redirect('projects:proyecto_list')
    return render(request, 'projects/simple_form.html', {'form': form, 'title': 'Crear proyecto'})


@login_required
@role_required('administrador', 'instructor', 'aprendiz')
def proyecto_update(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_proyectos_queryset(usuario), pk=pk)
    form = ProyectoForm(request.POST or None, instance=item)
    _apply_proyecto_form_permissions(form, usuario)
    if request.method == 'POST' and form.is_valid():
        proyecto = form.save()
        messages.success(request, 'Proyecto editado correctamente.')
        return redirect('projects:proyecto_list')
    return render(request, 'projects/simple_form.html', {'form': form, 'title': 'Editar proyecto'})


@login_required
@role_required('administrador', 'instructor')
def proyecto_delete(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_proyectos_queryset(usuario), pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Proyecto eliminado correctamente.')
    return redirect('projects:proyecto_list')


@login_required
def entregable_list(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    queryset = _filter_entregables(_entregables_queryset(usuario), _search_query(request))
    return render(request, 'projects/entregables_list.html', {'entregables': queryset})


@login_required
@role_required('administrador', 'instructor')
def entregable_create(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    ficha_id = _clean_filter_id(request.GET.get('ficha'))
    gaes_id = _clean_filter_id(request.GET.get('gaes'))
    destino = request.GET.get('destino') if request.GET.get('destino') in {'scrum', 'aprendiz'} else 'scrum'
    form = EntregableForm(request.POST or None, request.FILES or None)
    _apply_entregable_form_permissions(form, usuario, ficha_id=ficha_id, gaes_id=gaes_id, destino=destino)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        archivo = form.cleaned_data.get('archivo_upload')
        if _role_name(usuario) == 'aprendiz':
            item.aprendiz = _get_aprendiz_profile(usuario)
        elif destino == 'scrum':
            item.aprendiz = None
        elif not item.aprendiz:
            form.add_error('aprendiz', 'Selecciona el aprendiz que recibira este entregable individual.')
            context = {
                'form': form,
                'title': 'Crear entregable',
                'clear_filters_url': request.path,
                **_entregable_filter_context(usuario, ficha_id=ficha_id, gaes_id=gaes_id, destino=destino),
            }
            return render(request, 'projects/entregable_form.html', context)
        if archivo:
            item.archivo = archivo.read()
            item.nombre_archivo = archivo.name
            item.url = None
        item.save()
        if _role_name(usuario) == 'aprendiz':
            _notificar_instructores_por_entregable(item, 'registro')
        else:
            _notificar_aprendices_por_entregable(item, 'asignado')
        messages.success(request, 'Entregable creado correctamente.')
        return redirect('projects:entregable_list')
    context = {
        'form': form,
        'title': 'Crear entregable',
        'clear_filters_url': request.path,
        **_entregable_filter_context(usuario, ficha_id=ficha_id, gaes_id=gaes_id, destino=destino),
    }
    return render(request, 'projects/entregable_form.html', context)


@login_required
@role_required('administrador', 'instructor', 'aprendiz')
def entregable_update(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_entregables_queryset(usuario), pk=pk)
    if _role_name(usuario) == 'aprendiz':
        if _entregable_vencido(item):
            messages.error(request, 'La fecha limite de este entregable ya vencio. Solicita al instructor una nueva fecha si necesitas entregarlo.')
            return redirect('projects:entregable_list')
        form = EntregaEvidenciaForm(request.POST or None, request.FILES or None, initial={'url': item.url or ''})
        if request.method == 'POST' and form.is_valid():
            archivo = form.cleaned_data.get('archivo_upload')
            item.url = form.cleaned_data.get('url') or None
            if archivo:
                item.archivo = archivo.read()
                item.nombre_archivo = archivo.name
                item.url = None
            item.save(update_fields=['url', 'archivo', 'nombre_archivo'])
            _notificar_instructores_por_entregable(item, 'entrego')
            messages.success(request, 'Evidencia entregada correctamente.')
            return redirect('projects:entregable_list')
        return render(request, 'projects/entrega_evidencia_form.html', {'form': form, 'item': item, 'title': 'Entregar evidencia'})

    item_ficha_id = item.proyecto.gaes.ficha_id if item.proyecto and item.proyecto.gaes else None
    item_gaes_id = item.proyecto.gaes_id if item.proyecto else None
    ficha_id = _clean_filter_id(request.GET.get('ficha')) or item_ficha_id
    gaes_id = _clean_filter_id(request.GET.get('gaes')) or item_gaes_id
    destino = request.GET.get('destino') if request.GET.get('destino') in {'scrum', 'aprendiz'} else ('aprendiz' if item.aprendiz_id else 'scrum')
    form = EntregableForm(request.POST or None, request.FILES or None, instance=item)
    _apply_entregable_form_permissions(form, usuario, ficha_id=ficha_id, gaes_id=gaes_id, destino=destino)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        archivo = form.cleaned_data.get('archivo_upload')
        if _role_name(usuario) == 'aprendiz':
            item.aprendiz = _get_aprendiz_profile(usuario)
        elif destino == 'scrum':
            item.aprendiz = None
        elif not item.aprendiz:
            form.add_error('aprendiz', 'Selecciona el aprendiz que recibira este entregable individual.')
            context = {
                'form': form,
                'title': 'Editar entregable',
                'clear_filters_url': request.path,
                **_entregable_filter_context(usuario, ficha_id=ficha_id, gaes_id=gaes_id, destino=destino),
            }
            return render(request, 'projects/entregable_form.html', context)
        if archivo:
            item.archivo = archivo.read()
            item.nombre_archivo = archivo.name
            item.url = None
        item.save()
        _notificar_instructores_por_entregable(item, 'actualizo')
        messages.success(request, 'Entregable editado correctamente.')
        return redirect('projects:entregable_list')
    context = {
        'form': form,
        'title': 'Editar entregable',
        'clear_filters_url': request.path,
        **_entregable_filter_context(usuario, ficha_id=ficha_id, gaes_id=gaes_id, destino=destino),
    }
    return render(request, 'projects/entregable_form.html', context)


@login_required
@role_required('administrador', 'instructor')
def entregable_delete(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_entregables_queryset(usuario), pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Entregable eliminado correctamente.')
    return redirect('projects:entregable_list')


@login_required
def entregable_download(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_entregables_queryset(usuario), pk=pk)
    if item.archivo and item.nombre_archivo:
        response = HttpResponse(item.archivo, content_type='application/octet-stream')
        response['Content-Disposition'] = content_disposition_header('attachment', item.nombre_archivo)
        return response
    if item.url:
        return redirect(item.url)
    messages.error(request, 'Este entregable no tiene archivo ni enlace disponible.')
    return redirect('projects:entregable_list')


@login_required
def entregable_open(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_entregables_queryset(usuario), pk=pk)
    if not item.archivo and item.url:
        return render(
            request,
            'projects/entregable_preview.html',
            {
                'item': item,
                'preview_type': 'url',
                'external_url': item.url,
                'download_url': item.url,
            },
        )
    if item.archivo and item.nombre_archivo:
        content_type = mimetypes.guess_type(item.nombre_archivo)[0] or 'application/octet-stream'
        extension = Path(item.nombre_archivo).suffix.lower()
        preview_type = 'unsupported'
        text_content = ''
        docx_html = ''
        if content_type == 'application/pdf':
            preview_type = 'embed'
        elif content_type.startswith('image/'):
            preview_type = 'image'
        elif content_type in TEXT_PREVIEW_TYPES or content_type.startswith('text/'):
            preview_type = 'text'
            text_content = _decode_preview_text(item.archivo)
        elif extension == '.docx':
            preview_type = 'docx'
            docx_html = _docx_preview_html(item.archivo)
        return render(
            request,
            'projects/entregable_preview.html',
            {
                'item': item,
                'preview_type': preview_type,
                'content_type': content_type,
                'text_content': text_content,
                'docx_html': docx_html,
            },
        )
    messages.error(request, 'Este entregable no tiene archivo ni enlace disponible.')
    return redirect('projects:entregable_list')


@login_required
def entregable_inline(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_entregables_queryset(usuario), pk=pk)
    if item.archivo and item.nombre_archivo:
        content_type = mimetypes.guess_type(item.nombre_archivo)[0] or 'application/octet-stream'
        response = HttpResponse(item.archivo, content_type=content_type)
        response['Content-Disposition'] = content_disposition_header('inline', item.nombre_archivo)
        return response
    if item.url:
        return redirect(item.url)
    messages.error(request, 'Este entregable no tiene archivo ni enlace disponible.')
    return redirect('projects:entregable_list')


def _decode_preview_text(content: bytes) -> str:
    for encoding in ('utf-8', 'latin-1'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return 'No fue posible leer el contenido del archivo como texto.'


def _docx_preview_html(content: bytes) -> str:
    try:
        import mammoth
    except ImportError:
        return '<p>No esta instalada la libreria mammoth para previsualizar archivos DOCX.</p>'
    result = mammoth.convert_to_html(BytesIO(content))
    return result.value or '<p>El documento DOCX no contiene texto visible para previsualizar.</p>'


@login_required
@role_required('aprendiz')
def historial_trimestres(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    aprendiz, rows = _historial_trimestral_aprendiz(usuario)
    return render(
        request,
        'projects/historial_trimestres.html',
        {
            'aprendiz': aprendiz,
            'rows': rows,
        },
    )


@login_required
def evaluacion_list(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    queryset = _filter_evaluaciones(_evaluaciones_queryset(usuario), _search_query(request))
    return render(
        request,
        'projects/evaluaciones_list.html',
        {
            'evaluaciones': queryset,
            'aprendiz_actual': _get_aprendiz_profile(usuario),
            'aprendiz_gaes_ids': _get_aprendiz_gaes_ids(_get_aprendiz_profile(usuario)),
        },
    )


@login_required
@role_required('administrador', 'instructor')
def evaluacion_create(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    ficha_id = _clean_filter_id(request.GET.get('ficha'))
    gaes_id = _clean_filter_id(request.GET.get('gaes'))
    form = EvaluacionForm(request.POST or None)
    _apply_evaluacion_form_permissions(form, usuario, ficha_id=ficha_id, gaes_id=gaes_id)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        _notificar_aprendiz_por_evaluacion(item, 'registro')
        messages.success(request, 'Calificacion registrada correctamente.')
        return redirect('projects:evaluacion_list')
    context = {
        'form': form,
        'title': 'Calificar entregable',
        'clear_filters_url': request.path,
        **_evaluacion_filter_context(usuario, ficha_id=ficha_id, gaes_id=gaes_id),
    }
    return render(request, 'projects/evaluacion_form.html', context)


@login_required
@role_required('administrador', 'instructor')
def evaluacion_update(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_evaluaciones_queryset(usuario), pk=pk)
    item_ficha_id = item.gaes.ficha_id if item.gaes_id else None
    if not item_ficha_id and item.entregable and item.entregable.proyecto and item.entregable.proyecto.gaes:
        item_ficha_id = item.entregable.proyecto.gaes.ficha_id
    ficha_id = _clean_filter_id(request.GET.get('ficha')) or item_ficha_id
    gaes_id = _clean_filter_id(request.GET.get('gaes')) or item.gaes_id
    form = EvaluacionForm(request.POST or None, instance=item)
    _apply_evaluacion_form_permissions(form, usuario, ficha_id=ficha_id, gaes_id=gaes_id)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        _notificar_aprendiz_por_evaluacion(item, 'actualizo')
        messages.success(request, 'Calificacion editada correctamente.')
        return redirect('projects:evaluacion_list')
    context = {
        'form': form,
        'title': 'Editar calificacion',
        'clear_filters_url': request.path,
        **_evaluacion_filter_context(usuario, ficha_id=ficha_id, gaes_id=gaes_id),
    }
    return render(request, 'projects/evaluacion_form.html', context)


@login_required
@role_required('administrador', 'instructor')
def evaluacion_delete(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_current_user(request)
    item = get_object_or_404(_evaluaciones_queryset(usuario), pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Evaluacion eliminada correctamente.')
    return redirect('projects:evaluacion_list')


@login_required
@role_required('instructor')
def evaluacion_final_list(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    all_rows = _evaluacion_final_rows(usuario)
    selected_estado = request.GET.get('estado', '')
    selected_ficha_id = _clean_filter_id(request.GET.get('ficha'))
    query = _search_query(request).lower()
    fichas = Ficha.objects.filter(id__in={row['aprendiz'].ficha_id for row in all_rows}).order_by('codigo_ficha')
    rows_by_ficha = _filter_evaluacion_final_rows(all_rows, selected_ficha_id=selected_ficha_id)
    if query:
        rows_by_ficha = [
            row for row in rows_by_ficha
            if query in f"{row['aprendiz'].usuario.nombre} {row['aprendiz'].usuario.apellido}".lower()
            or query in row['aprendiz'].usuario.numero_documento.lower()
            or query in row['aprendiz'].ficha.codigo_ficha.lower()
            or query in f"{row['instructor'].usuario.nombre} {row['instructor'].usuario.apellido}".lower()
        ]
    total = len(rows_by_ficha)
    aprobados = sum(1 for row in rows_by_ficha if row['evaluacion_final'] and row['evaluacion_final'].estado == EvaluacionFinalTrimestre.Estado.APROBADO)
    no_aprobados = sum(1 for row in rows_by_ficha if row['evaluacion_final'] and row['evaluacion_final'].estado == EvaluacionFinalTrimestre.Estado.NO_APROBADO)
    pendientes = total - aprobados - no_aprobados
    rows = _filter_evaluacion_final_rows(rows_by_ficha, selected_estado=selected_estado)
    return render(
        request,
        'projects/evaluacion_final_list.html',
        {
            'rows': rows,
            'total_aprendices': total,
            'total_aprobados': aprobados,
            'total_no_aprobados': no_aprobados,
            'total_pendientes': pendientes,
            'selected_estado': selected_estado,
            'selected_ficha_id': selected_ficha_id,
            'fichas': fichas,
        },
    )


@login_required
@role_required('instructor')
def evaluacion_final_guardar(request: HttpRequest, aprendiz_id: int, trimestre_id: int, estado: str) -> HttpResponse:
    usuario = get_current_user(request)
    if request.method != 'POST':
        return redirect('projects:evaluacion_final_list')
    if estado not in {EvaluacionFinalTrimestre.Estado.APROBADO, EvaluacionFinalTrimestre.Estado.NO_APROBADO}:
        messages.error(request, 'No se pudo registrar el resultado. Intenta nuevamente.')
        return redirect('projects:evaluacion_final_list')

    instructor = get_object_or_404(_instructor_assignments(usuario), trimestre_id=trimestre_id)
    aprendiz = get_object_or_404(Aprendiz.objects.select_related('usuario', 'ficha'), pk=aprendiz_id, ficha=instructor.ficha)
    evaluacion_final, _created = EvaluacionFinalTrimestre.objects.update_or_create(
        aprendiz=aprendiz,
        trimestre=instructor.trimestre,
        defaults={
            'instructor': instructor,
            'estado': estado,
            'observaciones': request.POST.get('observaciones', '').strip(),
        },
    )
    _notificar_evaluacion_final(evaluacion_final)
    if estado == EvaluacionFinalTrimestre.Estado.APROBADO:
        messages.success(request, 'Evaluacion final registrada como aprobada correctamente.')
    else:
        messages.warning(request, 'Evaluacion final registrada como no aprobada correctamente.')
    return redirect('projects:evaluacion_final_list')


@login_required
@role_required('instructor')
def evaluacion_final_excel(request: HttpRequest) -> HttpResponse:
    headers, rows = _final_report_rows(
        get_current_user(request),
        selected_estado=request.GET.get('estado', ''),
        selected_ficha_id=_clean_filter_id(request.GET.get('ficha')),
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Evaluacion final'
    sheet.append(['Reporte de evaluacion final'])
    sheet.append([f'Generado: {timezone.localtime().strftime("%d/%m/%Y %I:%M %p")}'])
    sheet.append([])
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="evaluacion_final.xlsx"'
    return response


@login_required
@role_required('instructor')
def evaluacion_final_pdf(request: HttpRequest) -> HttpResponse:
    headers, rows = _final_report_rows(
        get_current_user(request),
        selected_estado=request.GET.get('estado', ''),
        selected_ficha_id=_clean_filter_id(request.GET.get('ficha')),
    )
    return pdf_response('evaluacion_final.pdf', 'Evaluación final', headers, rows)
