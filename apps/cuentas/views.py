"""Vistas del modulo de cuentas.

Primer bloque migrado a Django puro:
- login sin fetch/AJAX
- recuperacion de contraseña
- CRUD server-side de usuarios para administrador
"""

from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    LoginForm,
    PasswordRecoveryRequestForm,
    PasswordResetConfirmForm,
    ProfileRequestForm,
    ProfileUpdateConfirmForm,
    RegisterForm,
    UsuarioForm,
)
from .models import Notificacion, Rol, Usuario
from .services import (
    build_dashboard_name,
    clear_profile_update_code,
    create_or_update_password,
    create_profile_for_role,
    ensure_default_roles,
    is_strong_password,
    send_profile_update_code,
    send_password_reset_code,
    validate_profile_update_code,
    validate_reset_code,
    validate_unique_usuario_fields,
    PASSWORD_RESET_CODE_TTL,
)

PROFILE_UPDATE_PENDING_SESSION_KEY = 'gespro_profile_update_pending'
LOGIN_RATE_LIMIT_ATTEMPTS = 5
LOGIN_RATE_LIMIT_SECONDS = 5 * 60
PASSWORD_RECOVERY_RATE_LIMIT_ATTEMPTS = 5
PASSWORD_RECOVERY_RATE_LIMIT_SECONDS = 15 * 60


def _format_countdown_label(seconds: int) -> str:
    minutes, remaining_seconds = divmod(max(0, seconds), 60)
    return f'{minutes:02d}:{remaining_seconds:02d}'


def _usuario_label(usuario: Usuario) -> str:
    nombre = str(usuario).strip()
    return nombre or usuario.correo or f'usuario #{usuario.id}'


def _client_ip(request: HttpRequest) -> str:
    return request.META.get('REMOTE_ADDR') or 'unknown'


def _rate_limit_key(prefix: str, request: HttpRequest, identifier: str) -> str:
    normalized_identifier = (identifier or 'anonymous').strip().lower()
    return f'gespro:{prefix}:{_client_ip(request)}:{normalized_identifier}'


def _is_rate_limited(key: str, max_attempts: int) -> bool:
    return int(cache.get(key, 0) or 0) >= max_attempts


def _record_rate_limit_attempt(key: str, timeout: int) -> None:
    if cache.add(key, 1, timeout=timeout):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)


def _clear_rate_limit(key: str) -> None:
    cache.delete(key)


def get_current_user(request: HttpRequest) -> Usuario | None:
    user_id = request.session.get('gespro_user_id')
    if not user_id:
        return None
    usuario = Usuario.objects.select_related('rol').filter(id=user_id).first()
    if usuario and usuario.estado != Usuario.Estado.ACTIVO:
        request.session.flush()
        request.inactive_session_user = True
        return None
    return usuario


def login_required(view):
    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs):
        if get_current_user(request) is None:
            if getattr(request, 'inactive_session_user', False):
                messages.error(request, 'Tu cuenta esta inactiva. Comunicate con el administrador.')
            else:
                messages.warning(request, 'Debes iniciar sesión para continuar.')
            return redirect('accounts:login')
        return view(request, *args, **kwargs)

    return wrapper


def _save_pending_profile_photo(uploaded_file, usuario_id: int) -> str:
    extension = Path(uploaded_file.name or '').suffix.lower() or '.jpg'
    filename = f'profile_pending/{usuario_id}_{uuid4().hex}{extension}'
    return default_storage.save(filename, ContentFile(uploaded_file.read()))


def _build_profile_pending_data(usuario: Usuario, form: ProfileRequestForm, uploaded_file_path: str | None) -> dict:
    cleaned = form.cleaned_data
    photo_action = 'keep'
    foto_path = ''
    if cleaned.get('remove_photo'):
        photo_action = 'remove'
    elif uploaded_file_path:
        photo_action = 'replace'
        foto_path = uploaded_file_path

    return {
        'nombre': cleaned['nombre'].strip(),
        'apellido': cleaned['apellido'].strip(),
        'correo': cleaned['correo'].strip().lower(),
        'photo_action': photo_action,
        'foto_path': foto_path,
    }


def _profile_has_changes(usuario: Usuario, pending_data: dict) -> bool:
    if usuario.nombre != pending_data['nombre']:
        return True
    if usuario.apellido != pending_data['apellido']:
        return True
    if usuario.correo != pending_data['correo']:
        return True
    if pending_data['photo_action'] != 'keep':
        return True
    return False


def _clear_pending_profile_update(request: HttpRequest, usuario: Usuario) -> None:
    request.session.pop(PROFILE_UPDATE_PENDING_SESSION_KEY, None)
    clear_profile_update_code(usuario)


def _apply_profile_update(usuario: Usuario, pending_data: dict) -> None:
    update_fields = ['nombre', 'apellido', 'correo']
    usuario.nombre = pending_data['nombre']
    usuario.apellido = pending_data['apellido']
    usuario.correo = pending_data['correo']
    if pending_data.get('photo_action') == 'remove':
        if usuario.foto_perfil:
            usuario.foto_perfil.delete(save=False)
        usuario.foto_perfil = None
        update_fields.append('foto_perfil')
    elif pending_data.get('photo_action') == 'replace' and pending_data.get('foto_path'):
        if usuario.foto_perfil and usuario.foto_perfil.name != pending_data['foto_path']:
            usuario.foto_perfil.delete(save=False)
        usuario.foto_perfil.name = pending_data['foto_path']
        update_fields.append('foto_perfil')
    usuario.save(update_fields=update_fields)


def role_required(*roles: str):
    roles_normalized = {rol.lower() for rol in roles}

    def decorator(view):
        @wraps(view)
        def wrapper(request: HttpRequest, *args, **kwargs):
            usuario = get_current_user(request)
            if usuario is None:
                if getattr(request, 'inactive_session_user', False):
                    messages.error(request, 'Tu cuenta esta inactiva. Comunicate con el administrador.')
                return redirect('accounts:login')
            rol_nombre = usuario.rol.nombre_rol.lower() if usuario.rol else ''
            if rol_nombre not in roles_normalized:
                messages.error(request, 'No tienes permisos para acceder a este modulo.')
                return redirect('dashboards:home')
            request.current_usuario = usuario
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def index(request: HttpRequest) -> HttpResponse:
    return render(request, 'index.html', {'force_public_layout': True})


def register_view(request: HttpRequest) -> HttpResponse:
    ensure_default_roles()

    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        validation_error = validate_unique_usuario_fields(
            form.cleaned_data['correo'],
            form.cleaned_data['numero_documento'],
        )
        if validation_error:
            if 'correo' in validation_error.lower():
                form.add_error('correo', validation_error)
            else:
                form.add_error('numero_documento', validation_error)
        else:
            rol_aprendiz = Rol.objects.filter(nombre_rol__iexact='aprendiz').first()
            usuario = Usuario.objects.create(
                nombre=form.cleaned_data['nombre'].strip(),
                apellido=form.cleaned_data['apellido'].strip(),
                correo=form.cleaned_data['correo'].strip().lower(),
                password=make_password(form.cleaned_data['password']),
                tipo_documento=form.cleaned_data['tipo_documento'].strip(),
                numero_documento=form.cleaned_data['numero_documento'].strip(),
                rol=rol_aprendiz,
                estado=Usuario.Estado.ACTIVO,
                debe_cambiar_password=False,
                password_temporal=False,
            )
            create_profile_for_role(usuario)
            messages.success(request, f'Tu cuenta fue creada correctamente. Bienvenido a GESPRO, {_usuario_label(usuario)}.')
            return redirect('accounts:login')

    return render(request, 'accounts/register.html', {'form': form, 'force_public_layout': True})


def login_view(request: HttpRequest) -> HttpResponse:
    ensure_default_roles()

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        correo = form.cleaned_data['correo'].strip().lower()
        rate_key = _rate_limit_key('login', request, correo)
        if _is_rate_limited(rate_key, LOGIN_RATE_LIMIT_ATTEMPTS):
            messages.error(request, 'Demasiados intentos fallidos. Espera unos minutos antes de volver a intentar.')
            return render(
                request,
                'accounts/login.html',
                {
                    'form': form,
                    'force_public_layout': True,
                },
            )

        usuario = Usuario.objects.select_related('rol').filter(correo=correo).first()
        if usuario is None:
            _record_rate_limit_attempt(rate_key, LOGIN_RATE_LIMIT_SECONDS)
            messages.error(request, 'No encontramos una cuenta registrada con ese correo.')
        elif not check_password(form.cleaned_data['password'] or '', usuario.password):
            _record_rate_limit_attempt(rate_key, LOGIN_RATE_LIMIT_SECONDS)
            messages.error(request, 'La contraseña ingresada no corresponde a esta cuenta.')
        elif usuario.estado != Usuario.Estado.ACTIVO:
            messages.error(request, 'Tu cuenta esta inactiva. Comunicate con el administrador.')
        elif usuario.rol and usuario.rol.nombre_rol.lower() == 'instructor' and (
            usuario.debe_cambiar_password or usuario.password_temporal
        ):
            request.session['password_reset_prefill_correo'] = usuario.correo
            messages.warning(request, 'Antes de ingresar debes cambiar la contraseña temporal asignada.')
            return redirect(f"{reverse('accounts:password_recovery')}?correo={usuario.correo}")
        else:
            _clear_rate_limit(rate_key)
            request.session['gespro_user_id'] = usuario.id
            messages.success(request, f'Bienvenido, {_usuario_label(usuario)}. Ingresaste como {usuario.rol.nombre_rol}.')
            return redirect('dashboards:home')

    return render(
        request,
        'accounts/login.html',
        {
            'form': form,
            'force_public_layout': True,
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    if request.method != 'POST':
        return render(request, 'accounts/logout_confirm.html', {'force_public_layout': False})
    request.session.flush()
    messages.success(request, 'Cerraste sesión correctamente.')
    return redirect('accounts:login')


def password_recovery_request(request: HttpRequest) -> HttpResponse:
    ensure_default_roles()
    initial = {'correo': request.GET.get('correo') or request.session.get('password_reset_prefill_correo', '')}
    form = PasswordRecoveryRequestForm(request.POST or None, initial=initial)

    if request.method == 'POST' and form.is_valid():
        correo = form.cleaned_data['correo'].strip().lower()
        rate_key = _rate_limit_key('password-recovery', request, correo)
        if _is_rate_limited(rate_key, PASSWORD_RECOVERY_RATE_LIMIT_ATTEMPTS):
            messages.error(request, 'Has solicitado varios códigos. Espera unos minutos antes de intentar de nuevo.')
            return render(request, 'accounts/password_recovery_request.html', {'form': form, 'force_public_layout': True})

        usuario = Usuario.objects.filter(correo=correo).first()
        if not usuario:
            _record_rate_limit_attempt(rate_key, PASSWORD_RECOVERY_RATE_LIMIT_SECONDS)
            messages.success(request, 'Si el correo esta registrado, enviaremos un código de recuperación.')
        else:
            _record_rate_limit_attempt(rate_key, PASSWORD_RECOVERY_RATE_LIMIT_SECONDS)
            send_password_reset_code(usuario)
            request.session['password_reset_correo'] = usuario.correo
            expires_at = timezone.now() + timedelta(seconds=PASSWORD_RESET_CODE_TTL)
            request.session['password_reset_expires_at'] = expires_at.isoformat()
            messages.success(request, 'Si el correo esta registrado, enviaremos un código de recuperación.')
            return redirect('accounts:password_reset_confirm')

    return render(request, 'accounts/password_recovery_request.html', {'form': form, 'force_public_layout': True})


def password_reset_confirm(request: HttpRequest) -> HttpResponse:
    correo = request.session.get('password_reset_correo', '')
    expires_at_raw = request.session.get('password_reset_expires_at', '')
    if not correo:
        messages.warning(request, 'Primero solicita un código de recuperación para continuar.')
        return redirect('accounts:password_recovery')

    seconds_remaining = 0
    expires_at_label = ''
    countdown_labels = []
    if expires_at_raw:
        expires_at = datetime.fromisoformat(expires_at_raw)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)
        seconds_remaining = max(0, int((expires_at - timezone.now()).total_seconds()))
        expires_at_label = timezone.localtime(expires_at).strftime('%H:%M')
        countdown_labels = [_format_countdown_label(seconds) for seconds in range(seconds_remaining, -1, -1)]

    form = PasswordResetConfirmForm(request.POST or None, initial={'correo': correo})

    if request.method == 'POST' and form.is_valid():
        usuario = validate_reset_code(
            form.cleaned_data['correo'],
            form.cleaned_data['codigo'],
        )
        nueva_password = form.cleaned_data['nueva_password']
        if usuario is None:
            messages.error(request, 'El código es incorrecto o ya venció.')
        elif not is_strong_password(nueva_password):
            messages.error(request, 'La nueva contraseña no cumple los requisitos de seguridad.')
        else:
            create_or_update_password(usuario, nueva_password)
            request.session.pop('password_reset_correo', None)
            request.session.pop('password_reset_prefill_correo', None)
            request.session.pop('password_reset_expires_at', None)
            messages.success(request, 'Tu contraseña fue actualizada. Ahora puedes iniciar sesión.')
            return redirect('accounts:login')

    return render(
        request,
        'accounts/password_reset_confirm.html',
        {
            'form': form,
            'force_public_layout': True,
            'seconds_remaining': seconds_remaining,
            'expires_at_label': expires_at_label,
            'countdown_labels': countdown_labels,
        },
    )


@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    if usuario is None:
        return redirect('accounts:login')

    pending_profile = request.session.get(PROFILE_UPDATE_PENDING_SESSION_KEY)
    profile_form = ProfileRequestForm(instance=usuario, prefix='profile')
    confirm_form = ProfileUpdateConfirmForm(prefix='confirm')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'request_update':
            profile_form = ProfileRequestForm(request.POST, request.FILES, instance=usuario, prefix='profile')
            if profile_form.is_valid():
                validation_error = validate_unique_usuario_fields(
                    profile_form.cleaned_data['correo'],
                    usuario.numero_documento,
                    exclude_user_id=usuario.id,
                )
                if validation_error:
                    profile_form.add_error('correo', validation_error)
                else:
                    uploaded_file_path = None
                    uploaded_file = profile_form.cleaned_data.get('foto_perfil')
                    if uploaded_file:
                        uploaded_file_path = _save_pending_profile_photo(uploaded_file, usuario.id)
                    pending_data = _build_profile_pending_data(usuario, profile_form, uploaded_file_path)
                    if not _profile_has_changes(usuario, pending_data):
                        messages.info(request, 'No detectamos cambios nuevos en tu perfil.')
                    elif pending_data['correo'] == usuario.correo:
                        _apply_profile_update(usuario, pending_data)
                        _clear_pending_profile_update(request, usuario)
                        messages.success(request, 'Tu perfil fue actualizado correctamente.')
                        return redirect('accounts:profile')
                    else:
                        request.session[PROFILE_UPDATE_PENDING_SESSION_KEY] = pending_data
                        send_profile_update_code(usuario)
                        messages.success(
                            request,
                            f'Se envió un código de verificación al correo actual {usuario.correo}. Confirma el código para aplicar los cambios.',
                        )
                        return redirect('accounts:profile')
        elif action == 'confirm_update':
            confirm_form = ProfileUpdateConfirmForm(request.POST, prefix='confirm')
            if not pending_profile:
                messages.warning(request, 'Primero solicita la actualización del perfil para generar un código.')
            elif confirm_form.is_valid():
                if not validate_profile_update_code(usuario, confirm_form.cleaned_data['codigo']):
                    confirm_form.add_error('codigo', 'El código es incorrecto o ya venció.')
                else:
                    update_fields = ['nombre', 'apellido', 'correo']
                    usuario.nombre = pending_profile['nombre']
                    usuario.apellido = pending_profile['apellido']
                    usuario.correo = pending_profile['correo']
                    if pending_profile.get('photo_action') == 'remove':
                        if usuario.foto_perfil:
                            usuario.foto_perfil.delete(save=False)
                        usuario.foto_perfil = None
                        update_fields.append('foto_perfil')
                    elif pending_profile.get('photo_action') == 'replace' and pending_profile.get('foto_path'):
                        if usuario.foto_perfil and usuario.foto_perfil.name != pending_profile['foto_path']:
                            usuario.foto_perfil.delete(save=False)
                        usuario.foto_perfil.name = pending_profile['foto_path']
                        update_fields.append('foto_perfil')
                    usuario.save(update_fields=update_fields)
                    _clear_pending_profile_update(request, usuario)
                    messages.success(request, 'Tu perfil fue actualizado correctamente.')
                    return redirect('accounts:profile')
            profile_form = ProfileRequestForm(instance=usuario, prefix='profile')

    pending_profile = request.session.get(PROFILE_UPDATE_PENDING_SESSION_KEY)
    context = {
        'profile_form': profile_form,
        'confirm_form': confirm_form,
        'pending_profile': pending_profile,
        'usuario': usuario,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
@role_required('administrador')
def usuarios_list(request: HttpRequest) -> HttpResponse:
    usuarios = Usuario.objects.select_related('rol').order_by('id')
    query = request.GET.get('q', '').strip()
    if query:
        usuarios = usuarios.filter(
            Q(nombre__icontains=query)
            | Q(apellido__icontains=query)
            | Q(correo__icontains=query)
            | Q(tipo_documento__icontains=query)
            | Q(numero_documento__icontains=query)
            | Q(estado__icontains=query)
            | Q(rol__nombre_rol__icontains=query)
        )
    return render(request, 'accounts/usuarios_list.html', {'usuarios': usuarios})


@login_required
@role_required('administrador')
def usuarios_create(request: HttpRequest) -> HttpResponse:
    ensure_default_roles()
    form = UsuarioForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        validation_error = validate_unique_usuario_fields(form.cleaned_data['correo'], form.cleaned_data['numero_documento'])
        if validation_error:
            form.add_error('correo', validation_error)
        else:
            usuario = form.save(commit=False)
            raw_password = form.cleaned_data['password'] or 'Temporal123*'
            usuario.password = make_password(raw_password)
            rol_nombre = usuario.rol.nombre_rol.lower() if usuario.rol else ''
            usuario.debe_cambiar_password = rol_nombre == 'instructor'
            usuario.password_temporal = rol_nombre == 'instructor'
            usuario.save()
            create_profile_for_role(usuario)
            messages.success(request, 'Usuario creado correctamente.')
            return redirect('accounts:usuarios_list')

    return render(request, 'accounts/usuarios_form.html', {'form': form, 'title': 'Crear usuario'})


@login_required
@role_required('administrador')
def usuarios_update(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_object_or_404(Usuario, pk=pk)
    form = UsuarioForm(request.POST or None, instance=usuario)
    if request.method == 'POST' and form.is_valid():
        validation_error = validate_unique_usuario_fields(
            form.cleaned_data['correo'],
            form.cleaned_data['numero_documento'],
            exclude_user_id=usuario.id,
        )
        if validation_error:
            form.add_error('correo', validation_error)
        else:
            updated = form.save(commit=False)
            raw_password = form.cleaned_data['password']
            if raw_password:
                if not is_strong_password(raw_password):
                    form.add_error('password', 'La contraseña debe tener al menos 8 caracteres, mayúscula, minúscula, número y especial.')
                    return render(request, 'accounts/usuarios_form.html', {'form': form, 'title': 'Editar usuario'})
                updated.password = make_password(raw_password)
                updated.debe_cambiar_password = False
                updated.password_temporal = False
            else:
                rol_nombre = updated.rol.nombre_rol.lower() if updated.rol else ''
                if rol_nombre == 'instructor':
                    updated.debe_cambiar_password = True
                    updated.password_temporal = True
            updated.save()
            create_profile_for_role(updated)
            messages.success(request, 'Usuario editado correctamente.')
            return redirect('accounts:usuarios_list')

    return render(request, 'accounts/usuarios_form.html', {'form': form, 'title': 'Editar usuario'})


@login_required
@role_required('administrador')
def usuarios_toggle_estado(request: HttpRequest, pk: int) -> HttpResponse:
    usuario = get_object_or_404(Usuario, pk=pk)
    usuario.estado = Usuario.Estado.INACTIVO if usuario.estado == Usuario.Estado.ACTIVO else Usuario.Estado.ACTIVO
    usuario.save(update_fields=['estado'])
    if usuario.estado == Usuario.Estado.ACTIVO:
        messages.success(request, 'Usuario activado correctamente.')
    else:
        messages.success(request, 'Usuario desactivado correctamente.')
    return redirect('accounts:usuarios_list')


@login_required
def notificaciones_list(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    notificaciones = Notificacion.objects.filter(usuario=usuario)
    return render(request, 'accounts/notificaciones_list.html', {'notificaciones': notificaciones})


@login_required
def notificacion_marcar_leida(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != 'POST':
        return redirect('accounts:notificaciones_list')
    usuario = get_current_user(request)
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=usuario)
    notificacion.leida = True
    notificacion.save(update_fields=['leida'])
    if notificacion.url_destino:
        return redirect(notificacion.url_destino)
    return redirect('accounts:notificaciones_list')


@login_required
def notificacion_eliminar(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method != 'POST':
        return redirect('accounts:notificaciones_list')
    usuario = get_current_user(request)
    notificacion = get_object_or_404(Notificacion, pk=pk, usuario=usuario)
    notificacion.delete()
    messages.success(request, 'Se elimino la notificacion seleccionada.')
    return redirect('accounts:notificaciones_list')


@login_required
def notificaciones_marcar_todas(request: HttpRequest) -> HttpResponse:
    if request.method != 'POST':
        return redirect('accounts:notificaciones_list')
    usuario = get_current_user(request)
    Notificacion.objects.filter(usuario=usuario, leida=False).update(leida=True)
    messages.success(request, 'Todas tus notificaciones quedaron marcadas como leidas.')
    return redirect('accounts:notificaciones_list')


def redirect_by_role(request: HttpRequest) -> HttpResponse:
    usuario = get_current_user(request)
    if usuario is None:
        return redirect('accounts:login')
    dashboard_name = build_dashboard_name(usuario)
    return redirect('dashboards:panel', role=dashboard_name)
