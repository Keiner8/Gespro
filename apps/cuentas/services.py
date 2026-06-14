"""Utilidades compartidas del modulo de cuentas."""

import random
from datetime import date
from datetime import timedelta
from email.mime.image import MIMEImage

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, send_mail
from django.utils import timezone

from .models import Administrador, Rol, Usuario

PASSWORD_RESET_CODE_TTL = 60 * 3
PROFILE_UPDATE_CODE_TTL = 60 * 3


def normalize_text(value: str | None) -> str:
    return (value or '').strip()


def is_strong_password(value: str | None) -> bool:
    value = value or ''
    return (
        len(value) >= 8
        and any(ch.isupper() for ch in value)
        and any(ch.islower() for ch in value)
        and any(ch.isdigit() for ch in value)
        and any(not ch.isalnum() for ch in value)
    )


def ensure_default_roles() -> None:
    defaults = {1: 'administrador', 2: 'instructor', 3: 'aprendiz'}
    for role_id, nombre in defaults.items():
        Rol.objects.update_or_create(id=role_id, defaults={'nombre_rol': nombre})


def ensure_default_ficha():
    from apps.academico.models import Ficha

    ficha, _created = Ficha.objects.get_or_create(
        codigo_ficha='SIN-ASIGNAR',
        defaults={
            'programa_formacion': 'Pendiente de asignacion',
            'nivel': Ficha.Nivel.TECNICO,
            'jornada': Ficha.Jornada.MIXTA,
            'modalidad': Ficha.Modalidad.MIXTA,
            'fecha_inicio': date.today(),
            'fecha_fin': date.today(),
            'estado': Ficha.Estado.ACTIVA,
        },
    )
    return ficha


def validate_unique_usuario_fields(correo: str, numero_documento: str, exclude_user_id: int | None = None) -> str | None:
    correo = normalize_text(correo).lower()
    numero_documento = normalize_text(numero_documento)

    correo_qs = Usuario.objects.select_related('rol').filter(correo=correo)
    documento_qs = Usuario.objects.select_related('rol').filter(numero_documento=numero_documento)

    if exclude_user_id is not None:
        correo_qs = correo_qs.exclude(id=exclude_user_id)
        documento_qs = documento_qs.exclude(id=exclude_user_id)

    if correo and correo_qs.exists():
        return 'Este correo ya esta en uso por otro usuario.'
    if numero_documento and documento_qs.exists():
        return 'Este numero de documento ya esta en uso por otro usuario.'
    return None


def authenticate_usuario(correo: str, password: str) -> Usuario | None:
    usuario = Usuario.objects.filter(correo=normalize_text(correo).lower()).select_related('rol').first()
    if not usuario:
        return None
    if not check_password(password or '', usuario.password):
        return None
    return usuario


def create_or_update_password(usuario: Usuario, raw_password: str) -> None:
    usuario.password = make_password(raw_password)
    usuario.debe_cambiar_password = False
    usuario.password_temporal = False
    usuario.save(update_fields=['password', 'debe_cambiar_password', 'password_temporal'])


def build_dashboard_name(usuario: Usuario) -> str:
    rol_nombre = usuario.rol.nombre_rol.lower() if usuario.rol else ''
    if rol_nombre == 'administrador':
        return 'administrador'
    if rol_nombre == 'instructor':
        return 'instructor'
    return 'aprendiz'


def get_password_reset_cache_key(correo: str) -> str:
    return f'gespro-reset:{correo}'


def send_password_reset_code(usuario: Usuario) -> None:
    codigo = f'{random.randint(0, 999999):06d}'
    cache.set(
        get_password_reset_cache_key(usuario.correo),
        {'usuario_id': usuario.id, 'numero_documento': usuario.numero_documento, 'codigo': codigo},
        PASSWORD_RESET_CODE_TTL,
    )
    expires_at = timezone.localtime(timezone.now() + timedelta(seconds=PASSWORD_RESET_CODE_TTL)).strftime('%H:%M')
    minutes = PASSWORD_RESET_CODE_TTL // 60
    subject = 'Código de recuperación - GESPRO'
    text_message = (
        f'Hola {usuario.nombre},\n\n'
        f'Tu código de recuperación GESPRO es: {codigo}\n'
        f'Este código estará vigente hasta las {expires_at}.\n\n'
        'Si no solicitaste este cambio, ignora este mensaje.'
    )
    html_message = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Recuperación de contraseña</title>
    </head>
    <body style="margin:0; padding:0; background-color:#f4f7fb; font-family:Arial, sans-serif; color:#1f2937;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f7fb; padding:24px 12px;">
            <tr>
                <td align="center">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px; background:#ffffff; border-radius:18px; overflow:hidden; box-shadow:0 8px 30px rgba(15, 23, 42, 0.08);">
                        <tr>
                            <td style="background:linear-gradient(135deg, #1d4ed8, #7c3aed); padding:28px 24px; text-align:center;">
                                <div style="text-align:center; margin:0 auto 14px auto;">
                                    <img src="cid:logo3" alt="Logo GesPro" style="max-width:160px; width:100%; height:auto; display:block; margin:0 auto;">
                                </div>
                                <h1 style="margin:0; color:#ffffff; font-size:28px; line-height:1.2;">Recupera tu contraseña</h1>
                                <p style="margin:10px 0 0 0; color:#e9e7ff; font-size:15px; line-height:1.6;">
                                    Te ayudamos a volver a entrar a tu cuenta de forma segura en GesPro.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:32px 28px;">
                                <p style="margin:0 0 18px 0; font-size:16px; line-height:1.7;">
                                    Hola {usuario.nombre or "usuario"},
                                </p>
                                <p style="margin:0 0 18px 0; font-size:16px; line-height:1.7;">
                                    Recibimos una solicitud para restablecer tu contraseña en <strong>GesPro</strong>.
                                    Usa el siguiente código de verificación:
                                </p>
                                <div style="margin:28px 0; text-align:center;">
                                    <div style="display:inline-block; padding:16px 28px; border-radius:16px; background:#eef2ff; border:1px solid #c7d2fe;">
                                        <span style="display:block; font-size:34px; font-weight:700; letter-spacing:8px; color:#312e81;">
                                            {codigo}
                                        </span>
                                    </div>
                                </div>
                                <p style="margin:0 0 14px 0; font-size:15px; line-height:1.7; color:#4b5563;">
                                    Este código tiene una validez de <strong>{minutes} minutos</strong>.
                                </p>
                                <p style="margin:0 0 20px 0; font-size:15px; line-height:1.7; color:#4b5563;">
                                    Fecha límite aproximada: <strong>{expires_at}</strong>
                                </p>
                                <p style="margin:0 0 20px 0; font-size:15px; line-height:1.8; color:#4b5563;">
                                    Si no solicitaste este cambio, puedes ignorar este correo. Tu contraseña actual seguirá siendo la misma mientras no completes el proceso.
                                </p>
                                <p style="margin:24px 0 0 0; font-size:15px; line-height:1.7;">
                                    Un saludo,<br>
                                    <strong>Equipo GesPro</strong>
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding:18px 24px; background:#f8fafc; border-top:1px solid #e5e7eb; text-align:center;">
                                <p style="margin:0; font-size:13px; color:#6b7280; line-height:1.6;">
                                    Este es un mensaje automático de recuperación de contraseña.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    email = EmailMultiAlternatives(subject, text_message, settings.DEFAULT_FROM_EMAIL, [usuario.correo])
    email.attach_alternative(html_message, 'text/html')
    logo_path = settings.BASE_DIR / 'frontend_assets' / 'img' / 'logo3.png'
    if logo_path.exists():
        with logo_path.open('rb') as logo_file:
            logo = MIMEImage(logo_file.read())
        logo.add_header('Content-ID', '<logo3>')
        logo.add_header('Content-Disposition', 'inline', filename='logo3.png')
        email.attach(logo)
    email.send(fail_silently=False)


def validate_reset_code(correo: str, codigo: str) -> Usuario | None:
    usuario = Usuario.objects.filter(correo=normalize_text(correo).lower()).first()
    if not usuario:
        return None
    cache_data = cache.get(get_password_reset_cache_key(usuario.correo))
    if not cache_data:
        return None
    if cache_data.get('usuario_id') != usuario.id:
        return None
    if cache_data.get('codigo') != normalize_text(codigo):
        return None
    return usuario


def get_profile_update_cache_key(usuario_id: int) -> str:
    return f'gespro-profile-update:{usuario_id}'


def send_profile_update_code(usuario: Usuario) -> None:
    codigo = f'{random.randint(0, 999999):06d}'
    cache.set(
        get_profile_update_cache_key(usuario.id),
        {'usuario_id': usuario.id, 'codigo': codigo},
        PROFILE_UPDATE_CODE_TTL,
    )
    expires_at = timezone.localtime(timezone.now() + timedelta(seconds=PROFILE_UPDATE_CODE_TTL)).strftime('%H:%M')
    send_mail(
        subject='Verificación de cambios de perfil GESPRO',
        message=(
            f'Se solicitó una actualización de perfil para tu cuenta en GESPRO.\n'
            f'Tu código de verificación es {codigo}. Vigente hasta las {expires_at}.\n'
            'Si no realizaste esta solicitud, ignora este mensaje.'
        ),
        from_email=None,
        recipient_list=[usuario.correo],
        fail_silently=False,
    )


def validate_profile_update_code(usuario: Usuario, codigo: str) -> bool:
    cache_data = cache.get(get_profile_update_cache_key(usuario.id))
    if not cache_data:
        return False
    return cache_data.get('usuario_id') == usuario.id and cache_data.get('codigo') == normalize_text(codigo)


def clear_profile_update_code(usuario: Usuario) -> None:
    cache.delete(get_profile_update_cache_key(usuario.id))


def create_profile_for_role(usuario: Usuario) -> None:
    from apps.academico.models import Aprendiz, Ficha, Instructor

    rol_nombre = usuario.rol.nombre_rol.lower() if usuario.rol else ''
    if rol_nombre == 'administrador':
        Administrador.objects.get_or_create(usuario=usuario)
    elif rol_nombre == 'instructor':
        if not Instructor.objects.filter(usuario=usuario).exists():
            Instructor.objects.create(usuario=usuario)
    elif rol_nombre == 'aprendiz':
        ficha = Ficha.objects.order_by('id').first() or ensure_default_ficha()
        if ficha and not Aprendiz.objects.filter(usuario=usuario).exists():
            Aprendiz.objects.create(usuario=usuario, ficha=ficha)
