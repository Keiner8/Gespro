from __future__ import annotations

from datetime import date

from django.contrib.auth.hashers import make_password

from apps.cuentas.models import Rol, Usuario
from apps.academico.models import Aprendiz, AprendizGaes, Ficha, Gaes, Instructor, Trimestre
from apps.cuentas.services import ensure_default_roles


def force_business_login(client, usuario: Usuario) -> None:
    session = client.session
    session['gespro_user_id'] = usuario.id
    session.save()


def create_usuario(
    *,
    rol_nombre: str,
    correo: str,
    numero_documento: str,
    nombre: str = 'Test',
    apellido: str = 'User',
    password: str = 'Temporal123*',
) -> Usuario:
    ensure_default_roles()
    rol = Rol.objects.get(nombre_rol__iexact=rol_nombre)
    return Usuario.objects.create(
        nombre=nombre,
        apellido=apellido,
        correo=correo,
        password=make_password(password),
        tipo_documento='cc',
        numero_documento=numero_documento,
        rol=rol,
        estado=Usuario.Estado.ACTIVO,
    )


def create_ficha(codigo: str, programa: str = 'ADSO') -> Ficha:
    return Ficha.objects.create(
        codigo_ficha=codigo,
        programa_formacion=programa,
        nivel=Ficha.Nivel.TECNOLOGO,
        jornada=Ficha.Jornada.TARDE,
        modalidad=Ficha.Modalidad.PRESENCIAL,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 12, 31),
        estado=Ficha.Estado.ACTIVA,
    )


def create_trimestre(ficha: Ficha, numero: int = 1) -> Trimestre:
    return Trimestre.objects.create(
        numero=numero,
        ficha=ficha,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 3, 31),
        estado=Trimestre.Estado.ACTIVO,
    )


def create_gaes(ficha: Ficha, nombre: str) -> Gaes:
    return Gaes.objects.create(nombre=nombre, ficha=ficha)


def create_aprendiz(usuario: Usuario, ficha: Ficha, gaes: Gaes | None = None) -> Aprendiz:
    aprendiz = Aprendiz.objects.create(usuario=usuario, ficha=ficha)
    if gaes is not None:
        AprendizGaes.objects.create(aprendiz=aprendiz, gaes=gaes)
    return aprendiz


def create_instructor(usuario: Usuario, ficha: Ficha, especialidad: str = 'Backend', trimestre: Trimestre | None = None) -> Instructor:
    trimestre = trimestre or Trimestre.objects.filter(ficha=ficha).order_by('numero').first()
    return Instructor.objects.create(usuario=usuario, ficha=ficha, trimestre=trimestre, especialidad=especialidad)
