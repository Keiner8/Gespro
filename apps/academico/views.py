"""Vistas del modulo academico renderizadas por servidor."""

import csv
import unicodedata
from io import StringIO, TextIOWrapper

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.cuentas.models import Rol, Usuario
from apps.cuentas.services import ensure_default_roles, validate_unique_usuario_fields
from apps.cuentas.views import get_current_user, login_required, role_required

from .forms import (
    AprendizForm,
    BulkAprendizUploadForm,
    BulkInstructorUploadForm,
    FichaForm,
    GaesForm,
    InstructorForm,
    TrimestreForm,
)
from .models import Aprendiz, AprendizGaes, Ficha, Gaes, Instructor, Trimestre
from .services import ficha_cupos_disponibles, sync_aprendiz_gaes, sync_trimestres_for_ficha, validate_aprendiz_en_ficha


def _role_name(usuario) -> str:
    return usuario.rol.nombre_rol.lower() if usuario and usuario.rol else ''


def _current_usuario(request: HttpRequest):
    return getattr(request, 'current_usuario', None) or get_current_user(request)


def _usuario_label(usuario: Usuario) -> str:
    nombre = str(usuario).strip()
    return nombre or usuario.correo or f'usuario #{usuario.id}'


def _ficha_label(ficha: Ficha | None) -> str:
    return ficha.codigo_ficha if ficha else 'sin ficha'


def _aprendiz_label(aprendiz: Aprendiz) -> str:
    return _usuario_label(aprendiz.usuario)


def _instructor_label(instructor: Instructor) -> str:
    return _usuario_label(instructor.usuario)


def _instructor_ficha_ids(usuario) -> list[int]:
    if _role_name(usuario) != 'instructor':
        return []
    return list(
        Instructor.objects.filter(usuario=usuario, ficha__isnull=False)
        .values_list('ficha_id', flat=True)
        .distinct()
    )


def _instructor_trimestre_ids(usuario) -> list[int]:
    if _role_name(usuario) != 'instructor':
        return []
    return list(
        Instructor.objects.filter(usuario=usuario, trimestre__isnull=False)
        .values_list('trimestre_id', flat=True)
        .distinct()
    )


def _fichas_queryset(usuario):
    queryset = Ficha.objects.all().order_by('codigo_ficha')
    if _role_name(usuario) == 'instructor':
        queryset = queryset.filter(id__in=_instructor_ficha_ids(usuario))
    elif _role_name(usuario) == 'aprendiz':
        aprendiz = Aprendiz.objects.filter(usuario=usuario).first()
        queryset = queryset.filter(id=aprendiz.ficha_id) if aprendiz and aprendiz.ficha_id else queryset.none()
    return queryset


def _trimestres_queryset(usuario):
    queryset = Trimestre.objects.select_related('ficha').all()
    if _role_name(usuario) == 'instructor':
        queryset = queryset.filter(id__in=_instructor_trimestre_ids(usuario))
    return queryset


def _gaes_queryset(usuario):
    queryset = Gaes.objects.select_related('ficha').prefetch_related(
        'aprendiz_links__aprendiz__usuario',
        'aprendiz_links__aprendiz__ficha',
    )
    if _role_name(usuario) == 'instructor':
        queryset = queryset.filter(ficha_id__in=_instructor_ficha_ids(usuario))
    elif _role_name(usuario) == 'aprendiz':
        queryset = queryset.filter(aprendiz_links__aprendiz__usuario=usuario).distinct()
    return queryset


def _get_aprendiz_actual(usuario):
    if _role_name(usuario) != 'aprendiz':
        return None
    return Aprendiz.objects.filter(usuario=usuario).first()


def _instructor_ficha_resumenes(usuario):
    ficha_ids = _instructor_ficha_ids(usuario)
    fichas = (
        Ficha.objects.filter(id__in=ficha_ids)
        .prefetch_related('gaes__aprendiz_links__aprendiz__usuario', 'aprendices__usuario')
        .order_by('codigo_ficha')
    )
    resumenes = []
    for ficha in fichas:
        aprendices = list(ficha.aprendices.all())
        equipos = list(ficha.gaes.all())
        aprendices_asignados = set()
        equipos_detalle = []
        for equipo in equipos:
            integrantes = [link.aprendiz for link in equipo.aprendiz_links.all()]
            aprendices_asignados.update(aprendiz.id for aprendiz in integrantes)
            equipos_detalle.append(
                {
                    'equipo': equipo,
                    'integrantes': integrantes,
                    'integrantes_count': len(integrantes),
                }
            )
        aprendices_sin_scrum = [aprendiz for aprendiz in aprendices if aprendiz.id not in aprendices_asignados]
        resumenes.append(
            {
                'ficha': ficha,
                'aprendices': aprendices,
                'equipos': equipos,
                'equipos_detalle': equipos_detalle,
                'aprendices_sin_scrum': aprendices_sin_scrum,
                'aprendices_count': len(aprendices),
                'equipos_count': len(equipos),
            }
        )
    return resumenes


def _aprendices_queryset(usuario):
    queryset = Aprendiz.objects.select_related('usuario', 'usuario__rol', 'ficha').filter(
        usuario__rol__nombre_rol__iexact='aprendiz',
    )
    if _role_name(usuario) == 'instructor':
        queryset = queryset.filter(ficha_id__in=_instructor_ficha_ids(usuario))
    return queryset


def _instructores_queryset(usuario):
    queryset = Instructor.objects.select_related('usuario', 'usuario__rol', 'ficha', 'trimestre').filter(
        usuario__rol__nombre_rol__iexact='instructor',
    )
    if _role_name(usuario) == 'instructor':
        ficha_ids = _instructor_ficha_ids(usuario)
        queryset = queryset.filter(ficha_id__in=ficha_ids)
    return queryset


def _clean_filter_id(value):
    return int(value) if value and str(value).isdigit() else None


def _search_query(request: HttpRequest) -> str:
    return request.GET.get('q', '').strip()


def _filter_fichas(queryset, query: str):
    if not query:
        return queryset
    return queryset.filter(
        Q(codigo_ficha__icontains=query)
        | Q(programa_formacion__icontains=query)
        | Q(nivel__icontains=query)
        | Q(jornada__icontains=query)
        | Q(modalidad__icontains=query)
        | Q(estado__icontains=query)
    )


def _filter_trimestres(queryset, query: str):
    if not query:
        return queryset
    filters = (
        Q(ficha__codigo_ficha__icontains=query)
        | Q(ficha__programa_formacion__icontains=query)
        | Q(estado__icontains=query)
    )
    if query.isdigit():
        filters |= Q(numero=int(query))
    return queryset.filter(filters)


def _filter_aprendices(queryset, query: str):
    if not query:
        return queryset
    return queryset.filter(
        Q(usuario__nombre__icontains=query)
        | Q(usuario__apellido__icontains=query)
        | Q(usuario__correo__icontains=query)
        | Q(usuario__tipo_documento__icontains=query)
        | Q(usuario__numero_documento__icontains=query)
        | Q(ficha__codigo_ficha__icontains=query)
        | Q(ficha__programa_formacion__icontains=query)
    )


def _filter_instructores(queryset, query: str):
    if not query:
        return queryset
    filters = (
        Q(usuario__nombre__icontains=query)
        | Q(usuario__apellido__icontains=query)
        | Q(usuario__correo__icontains=query)
        | Q(usuario__tipo_documento__icontains=query)
        | Q(usuario__numero_documento__icontains=query)
        | Q(ficha__codigo_ficha__icontains=query)
        | Q(ficha__programa_formacion__icontains=query)
        | Q(especialidad__icontains=query)
    )
    if query.isdigit():
        filters |= Q(trimestre__numero=int(query))
    return queryset.filter(filters)


def _filter_equipos(queryset, query: str):
    if not query:
        return queryset
    return queryset.filter(
        Q(nombre__icontains=query)
        | Q(ficha__codigo_ficha__icontains=query)
        | Q(ficha__programa_formacion__icontains=query)
        | Q(aprendiz_links__aprendiz__usuario__nombre__icontains=query)
        | Q(aprendiz_links__aprendiz__usuario__apellido__icontains=query)
    ).distinct()


def _gaes_form_context(usuario, selected_ficha_id=None, equipo=None):
    fichas = _fichas_queryset(usuario)
    if not selected_ficha_id and equipo:
        selected_ficha_id = equipo.ficha_id

    aprendices = Aprendiz.objects.none()
    if selected_ficha_id:
        aprendices = (
            _aprendices_queryset(usuario)
            .filter(ficha_id=selected_ficha_id)
            .select_related('usuario', 'ficha')
            .prefetch_related('gaes_links__gaes')
            .order_by('usuario__nombre', 'usuario__apellido')
        )

    integrantes_actuales = set()
    if equipo:
        integrantes_actuales = set(
            AprendizGaes.objects.filter(gaes=equipo).values_list('aprendiz_id', flat=True)
        )

    aprendiz_rows = []
    for aprendiz in aprendices:
        gaes_link = aprendiz.gaes_links.select_related('gaes').first()
        equipo_actual = gaes_link.gaes if gaes_link else None
        pertenece_actual = aprendiz.id in integrantes_actuales
        bloqueado = bool(equipo_actual and not pertenece_actual)
        aprendiz_rows.append(
            {
                'aprendiz': aprendiz,
                'equipo_actual': equipo_actual,
                'pertenece_actual': pertenece_actual,
                'bloqueado': bloqueado,
            }
        )

    return {
        'fichas': fichas,
        'selected_ficha_id': selected_ficha_id,
        'aprendiz_rows': aprendiz_rows,
    }


def _sync_gaes_members(equipo: Gaes, aprendiz_ids: list[str], usuario):
    allowed_ids = set(
        _aprendices_queryset(usuario)
        .filter(ficha=equipo.ficha)
        .values_list('id', flat=True)
    )
    selected_ids = {int(value) for value in aprendiz_ids if value.isdigit()}
    selected_ids &= allowed_ids

    blocked_ids = set(
        AprendizGaes.objects.filter(aprendiz_id__in=selected_ids)
        .exclude(gaes=equipo)
        .values_list('aprendiz_id', flat=True)
    )
    selected_ids -= blocked_ids

    AprendizGaes.objects.filter(gaes=equipo).exclude(aprendiz_id__in=selected_ids).delete()
    for aprendiz_id in selected_ids:
        AprendizGaes.objects.get_or_create(aprendiz_id=aprendiz_id, gaes=equipo)

    return len(blocked_ids)


@login_required
@role_required('administrador', 'instructor', 'aprendiz')
def ficha_list(request: HttpRequest) -> HttpResponse:
    usuario = _current_usuario(request)
    fichas = _filter_fichas(_fichas_queryset(usuario), _search_query(request))
    context = {'fichas': fichas}
    if _role_name(usuario) == 'instructor':
        context['ficha_resumenes'] = _instructor_ficha_resumenes(usuario)
    return render(request, 'academic/fichas_list.html', context)


@login_required
@role_required('administrador')
def ficha_create(request: HttpRequest) -> HttpResponse:
    form = FichaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        ficha = form.save()
        sync_trimestres_for_ficha(ficha)
        messages.success(request, 'Ficha creada correctamente.')
        return redirect('academic:ficha_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Crear ficha'})


@login_required
@role_required('administrador')
def ficha_update(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Ficha, pk=pk)
    form = FichaForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        ficha = form.save()
        sync_trimestres_for_ficha(ficha)
        messages.success(request, 'Ficha editada correctamente.')
        return redirect('academic:ficha_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Editar ficha'})


@login_required
@role_required('administrador')
def ficha_delete(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Ficha, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Ficha eliminada correctamente.')
    return redirect('academic:ficha_list')


@login_required
@role_required('administrador', 'instructor')
def trimestre_list(request: HttpRequest) -> HttpResponse:
    usuario = _current_usuario(request)
    trimestres = _filter_trimestres(_trimestres_queryset(usuario), _search_query(request))
    grupos_map = {}
    for trimestre in trimestres:
        ficha = trimestre.ficha
        if ficha.id not in grupos_map:
            grupos_map[ficha.id] = {
                'ficha': ficha,
                'trimestres': [],
            }
        grupos_map[ficha.id]['trimestres'].append(trimestre)

    grupos = []
    for grupo in grupos_map.values():
        trimestres_grupo = grupo['trimestres']
        estados = {item.estado for item in trimestres_grupo}
        if Trimestre.Estado.ACTIVO in estados:
            estado_general = Trimestre.Estado.ACTIVO
        elif Trimestre.Estado.PENDIENTE in estados:
            estado_general = Trimestre.Estado.PENDIENTE
        else:
            estado_general = Trimestre.Estado.FINALIZADO

        grupo['total'] = len(trimestres_grupo)
        grupo['fecha_inicio'] = trimestres_grupo[0].fecha_inicio
        grupo['fecha_fin'] = trimestres_grupo[-1].fecha_fin
        grupo['estado_general'] = estado_general
        grupos.append(grupo)

    return render(
        request,
        'academic/trimestres_list.html',
        {
            'trimestres': trimestres,
            'trimestre_grupos': grupos,
        },
    )


@login_required
@role_required('administrador')
def trimestre_create(request: HttpRequest) -> HttpResponse:
    form = TrimestreForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        trimestre = form.save()
        messages.success(request, 'Trimestre creado correctamente.')
        return redirect('academic:trimestre_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Crear trimestre'})


@login_required
@role_required('administrador')
def trimestre_update(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Trimestre, pk=pk)
    form = TrimestreForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        trimestre = form.save()
        messages.success(request, 'Trimestre editado correctamente.')
        return redirect('academic:trimestre_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Editar trimestre'})


@login_required
@role_required('administrador')
def trimestre_delete(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Trimestre, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Trimestre eliminado correctamente.')
    return redirect('academic:trimestre_list')


@login_required
@role_required('instructor', 'aprendiz')
def gaes_list(request: HttpRequest) -> HttpResponse:
    usuario = _current_usuario(request)
    equipos = _filter_equipos(_gaes_queryset(usuario), _search_query(request))
    context = {
        'equipos': equipos,
        'aprendiz_actual': _get_aprendiz_actual(usuario),
    }
    if _role_name(usuario) == 'instructor':
        context['ficha_resumenes'] = _instructor_ficha_resumenes(usuario)
    return render(request, 'academic/gaes_list.html', context)


@login_required
@role_required('instructor')
def gaes_create(request: HttpRequest) -> HttpResponse:
    usuario = _current_usuario(request)
    selected_ficha_id = _clean_filter_id(request.GET.get('ficha'))
    form = GaesForm(request.POST or None, initial={'ficha': selected_ficha_id} if selected_ficha_id else None)
    if _role_name(usuario) == 'instructor':
        form.fields['ficha'].queryset = _fichas_queryset(usuario)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        blocked_count = _sync_gaes_members(item, request.POST.getlist('aprendices'), usuario)
        messages.success(request, 'Equipo Scrum creado correctamente.')
        if blocked_count:
            messages.warning(request, f'{blocked_count} aprendiz(es) no se agregaron porque ya pertenecen a otro equipo Scrum.')
        return redirect('academic:gaes_list')
    context = {
        'form': form,
        'title': 'Crear equipo Scrum',
        'clear_filters_url': request.path,
        **_gaes_form_context(usuario, selected_ficha_id=selected_ficha_id),
    }
    return render(request, 'academic/gaes_form.html', context)


@login_required
@role_required('instructor')
def gaes_update(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = _current_usuario(request)
    item = get_object_or_404(_gaes_queryset(usuario), pk=pk)
    selected_ficha_id = _clean_filter_id(request.GET.get('ficha')) or item.ficha_id
    form = GaesForm(request.POST or None, instance=item)
    if _role_name(usuario) == 'instructor':
        form.fields['ficha'].queryset = _fichas_queryset(usuario)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        blocked_count = _sync_gaes_members(item, request.POST.getlist('aprendices'), usuario)
        messages.success(request, 'Equipo Scrum editado correctamente.')
        if blocked_count:
            messages.warning(request, f'{blocked_count} aprendiz(es) no se agregaron porque ya pertenecen a otro equipo Scrum.')
        return redirect('academic:gaes_list')
    context = {
        'form': form,
        'title': 'Editar equipo Scrum',
        'clear_filters_url': request.path,
        **_gaes_form_context(usuario, selected_ficha_id=selected_ficha_id, equipo=item),
    }
    return render(request, 'academic/gaes_form.html', context)


@login_required
@role_required('instructor')
def gaes_delete(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = _current_usuario(request)
    item = get_object_or_404(_gaes_queryset(usuario), pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Equipo Scrum eliminado correctamente.')
    return redirect('academic:gaes_list')


@login_required
@role_required('administrador', 'instructor')
def aprendiz_list(request: HttpRequest) -> HttpResponse:
    usuario = _current_usuario(request)
    aprendices = _filter_aprendices(_aprendices_queryset(usuario), _search_query(request))
    return render(request, 'academic/aprendices_list.html', {'aprendices': aprendices})


@login_required
@role_required('administrador')
def aprendiz_create(request: HttpRequest) -> HttpResponse:
    form = AprendizForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        usuario = form.cleaned_data['usuario']
        ficha = form.cleaned_data['ficha']
        validation_error = validate_aprendiz_en_ficha(usuario, ficha)
        if validation_error:
            form.add_error('usuario', validation_error)
        elif ficha_cupos_disponibles(ficha) <= 0:
            form.add_error('ficha', 'La ficha seleccionada ya alcanzo el maximo recomendado de aprendices.')
        else:
            Aprendiz.objects.create(usuario=usuario, ficha=ficha)
            messages.success(request, 'Aprendiz creado correctamente.')
            return redirect('academic:aprendiz_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Registrar aprendiz'})


@login_required
@role_required('administrador')
def aprendiz_update(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Aprendiz, pk=pk)
    form = AprendizForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        usuario = form.cleaned_data['usuario']
        ficha = form.cleaned_data['ficha']
        validation_error = validate_aprendiz_en_ficha(usuario, ficha, exclude_aprendiz_id=item.id)
        if validation_error:
            form.add_error('usuario', validation_error)
        else:
            item.usuario = usuario
            item.ficha = ficha
            item.save()
            messages.success(request, 'Aprendiz editado correctamente.')
            return redirect('academic:aprendiz_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Editar aprendiz'})


@login_required
@role_required('administrador')
def aprendiz_delete(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Aprendiz, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Aprendiz eliminado correctamente.')
    return redirect('academic:aprendiz_list')


@login_required
@role_required('administrador')
def instructor_list(request: HttpRequest) -> HttpResponse:
    usuario = _current_usuario(request)
    instructores = _filter_instructores(_instructores_queryset(usuario), _search_query(request))
    return render(request, 'academic/instructores_list.html', {'instructores': instructores})


@login_required
@role_required('administrador')
def instructor_create(request: HttpRequest) -> HttpResponse:
    form = InstructorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Instructor creado correctamente.')
        return redirect('academic:instructor_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Registrar instructor'})


@login_required
@role_required('administrador')
def instructor_update(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Instructor, pk=pk)
    form = InstructorForm(request.POST or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Instructor editado correctamente.')
        return redirect('academic:instructor_list')
    return render(request, 'academic/simple_form.html', {'form': form, 'title': 'Editar instructor'})


@login_required
@role_required('administrador')
def instructor_delete(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Instructor, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Instructor eliminado correctamente.')
    return redirect('academic:instructor_list')


CSV_REQUIRED_USER_COLUMNS = {'nombre', 'apellido', 'correo', 'tipo_documento', 'numero_documento'}
CSV_HEADER_ALIASES = {
    'email': 'correo',
    'e_mail': 'correo',
    'tipo_de_documento': 'tipo_documento',
    'documento_tipo': 'tipo_documento',
    'numero_de_documento': 'numero_documento',
    'numero_documento_': 'numero_documento',
    'documento': 'numero_documento',
    'num_documento': 'numero_documento',
}


def _normalize_csv_header(field: str | None) -> str:
    value = (field or '').replace('\ufeff', '').strip().lower()
    value = ''.join(
        char
        for char in unicodedata.normalize('NFKD', value)
        if not unicodedata.combining(char)
    )
    value = value.replace('-', '_').replace(' ', '_').replace('__', '_').strip('_')
    return CSV_HEADER_ALIASES.get(value, value)


def _normalize_reader_fieldnames(reader) -> None:
    if reader.fieldnames:
        reader.fieldnames = [_normalize_csv_header(field) for field in reader.fieldnames]


def _open_csv_file(uploaded_file):
    text_file = TextIOWrapper(uploaded_file.file, encoding='utf-8-sig', newline='')
    content = text_file.read()
    if not content.strip():
        return csv.DictReader(StringIO(''))

    candidates = []
    try:
        candidates.append(csv.Sniffer().sniff(content[:4096], delimiters=',;\t'))
    except csv.Error:
        pass

    for delimiter in (',', ';', '\t'):
        dialect = csv.excel()
        dialect.delimiter = delimiter
        candidates.append(dialect)

    for dialect in candidates:
        reader = csv.DictReader(StringIO(content), dialect=dialect)
        _normalize_reader_fieldnames(reader)
        if CSV_REQUIRED_USER_COLUMNS.issubset(set(reader.fieldnames or [])):
            return reader

    reader = csv.DictReader(StringIO(content))
    _normalize_reader_fieldnames(reader)
    return reader


def _normalize_csv_value(row, key: str) -> str:
    return str(row.get(key) or '').strip()


def _csv_row_debug(row: dict) -> str:
    columnas = ', '.join(str(key) for key in row.keys()) or 'sin columnas'
    muestra = []
    for key, value in list(row.items())[:5]:
        clean_value = str(value or '').replace('\n', ' ').replace('\r', ' ').strip()
        if len(clean_value) > 45:
            clean_value = clean_value[:45] + '...'
        muestra.append(f'{key}={clean_value}')
    datos = ' | '.join(muestra) or 'sin datos'
    return f'Columnas detectadas: {columnas}. Datos recibidos: {datos}.'


def _coerce_user_csv_row(row: dict) -> dict:
    normalized = {
        _normalize_csv_header(key): value
        for key, value in row.items()
        if key is not None
    }
    if CSV_REQUIRED_USER_COLUMNS.issubset(set(normalized)):
        return normalized

    for key, value in row.items():
        header_text = str(key or '')
        value_text = str(value or '')
        for delimiter in (',', ';', '\t'):
            if delimiter not in header_text:
                continue
            headers = [_normalize_csv_header(part) for part in header_text.split(delimiter)]
            values = [part.strip() for part in value_text.split(delimiter)]
            if len(values) < len(headers):
                continue
            rebuilt = dict(zip(headers, values))
            if CSV_REQUIRED_USER_COLUMNS.issubset(set(rebuilt)):
                return rebuilt

    return normalized


def _get_role(nombre_rol: str) -> Rol:
    ensure_default_roles()
    return Rol.objects.get(nombre_rol__iexact=nombre_rol)


def _create_or_get_usuario_from_row(row, role_name: str):
    raw_row = row
    row = _coerce_user_csv_row(row)
    correo = _normalize_csv_value(row, 'correo').lower()
    numero_documento = _normalize_csv_value(row, 'numero_documento')
    nombre = _normalize_csv_value(row, 'nombre')
    apellido = _normalize_csv_value(row, 'apellido')
    tipo_documento = _normalize_csv_value(row, 'tipo_documento')
    role = _get_role(role_name)

    if not all([correo, numero_documento, nombre, apellido, tipo_documento]):
        faltantes = [
            label
            for label, value in [
                ('nombre', nombre),
                ('apellido', apellido),
                ('correo', correo),
                ('tipo_documento', tipo_documento),
                ('numero_documento', numero_documento),
            ]
            if not value
        ]
        return None, (
            'Faltan columnas o datos obligatorios: '
            f'{", ".join(faltantes)}. Usa: nombre, apellido, correo, tipo_documento, numero_documento. '
            f'{_csv_row_debug(row)} Original: {_csv_row_debug(raw_row)}'
        )

    usuario = Usuario.objects.filter(correo=correo).first()
    if usuario:
        if usuario.rol_id != role.id:
            return None, f'El correo {correo} ya existe con otro rol.'
        return usuario, None

    validation_error = validate_unique_usuario_fields(correo, numero_documento)
    if validation_error:
        return None, validation_error

    usuario = Usuario.objects.create(
        nombre=nombre,
        apellido=apellido,
        correo=correo,
        password=make_password('Temporal123*'),
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
        rol=role,
        estado=Usuario.Estado.ACTIVO,
        debe_cambiar_password=(role_name in {'instructor', 'aprendiz'}),
        password_temporal=(role_name in {'instructor', 'aprendiz'}),
    )
    return usuario, None


@login_required
@role_required('administrador')
def aprendices_bulk_upload(request: HttpRequest) -> HttpResponse:
    form = BulkAprendizUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        creados = 0
        errores: list[str] = []
        ficha = form.cleaned_data['ficha']
        reader = _open_csv_file(form.cleaned_data['archivo'])
        for index, row in enumerate(reader, start=2):
            try:
                usuario, error = _create_or_get_usuario_from_row(row, 'aprendiz')
                if error:
                    errores.append(f'Fila {index}: {error}')
                    continue

                validation_error = validate_aprendiz_en_ficha(usuario, ficha)
                if validation_error:
                    errores.append(f'Fila {index}: {validation_error}')
                    continue

                if ficha_cupos_disponibles(ficha) <= 0:
                    errores.append(f'Fila {index}: la ficha {ficha.codigo_ficha} no tiene cupos disponibles.')
                    continue

                Aprendiz.objects.create(usuario=usuario, ficha=ficha)
                creados += 1
            except Exception as exc:  # pragma: no cover - mensaje de respaldo
                errores.append(f'Fila {index}: {exc}')

        if creados:
            messages.success(request, f'Se cargaron {creados} aprendices correctamente.')
        for error in errores[:10]:
            messages.error(request, error)
        if len(errores) > 10:
            messages.warning(request, f'Se omitieron {len(errores) - 10} errores adicionales en pantalla.')
        return redirect('academic:aprendiz_list')

    return render(
        request,
        'academic/simple_form.html',
        {
            'form': form,
            'title': 'Carga masiva de aprendices',
            'subtitle': 'Selecciona una ficha y carga un archivo CSV con los aprendices que pertenecen a ella.',
        },
    )


@login_required
@role_required('administrador')
def instructores_bulk_upload(request: HttpRequest) -> HttpResponse:
    form = BulkInstructorUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        creados = 0
        errores: list[str] = []
        reader = _open_csv_file(form.cleaned_data['archivo'])
        for index, row in enumerate(reader, start=2):
            try:
                usuario, error = _create_or_get_usuario_from_row(row, 'instructor')
                if error:
                    errores.append(f'Fila {index}: {error}')
                    continue

                ficha_codigo = _normalize_csv_value(row, 'ficha_codigo')
                trimestre_numero = _normalize_csv_value(row, 'trimestre_numero')
                especialidad = _normalize_csv_value(row, 'especialidad')
                ficha = Ficha.objects.filter(codigo_ficha=ficha_codigo).first() if ficha_codigo else None
                if ficha_codigo and not ficha:
                    errores.append(f'Fila {index}: la ficha {ficha_codigo} no existe.')
                    continue
                trimestre = None
                if trimestre_numero and ficha:
                    trimestre = Trimestre.objects.filter(ficha=ficha, numero=trimestre_numero).first()
                    if not trimestre:
                        errores.append(f'Fila {index}: el trimestre {trimestre_numero} no existe para la ficha {ficha_codigo}.')
                        continue

                instructor = Instructor.objects.filter(usuario=usuario).first()
                if instructor:
                    instructor.ficha = ficha
                    instructor.trimestre = trimestre
                    instructor.especialidad = especialidad
                    instructor.save(update_fields=['ficha', 'trimestre', 'especialidad'])
                else:
                    Instructor.objects.create(
                        usuario=usuario,
                        ficha=ficha,
                        trimestre=trimestre,
                        especialidad=especialidad,
                    )
                creados += 1
            except Exception as exc:  # pragma: no cover - mensaje de respaldo
                errores.append(f'Fila {index}: {exc}')

        if creados:
            messages.success(request, f'Se cargaron {creados} instructores correctamente.')
        for error in errores[:10]:
            messages.error(request, error)
        if len(errores) > 10:
            messages.warning(request, f'Se omitieron {len(errores) - 10} errores adicionales en pantalla.')
        return redirect('academic:instructor_list')

    return render(
        request,
        'academic/simple_form.html',
        {
            'form': form,
            'title': 'Carga masiva de instructores',
            'subtitle': 'Carga un archivo CSV con instructores, ficha y especialidad.',
        },
    )
