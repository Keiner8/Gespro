"""Modelos del dominio de cuentas y control de acceso."""

from django.db import models


class Rol(models.Model):
    """Roles base usados para dividir acceso por panel y CRUD."""

    nombre_rol = models.CharField(max_length=50)

    class Meta:
        db_table = 'rol'
        ordering = ['id']

    def __str__(self) -> str:
        return self.nombre_rol


class Usuario(models.Model):
    """Usuario de negocio del proyecto, separado del auth nativo de Django."""

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'

    nombre = models.CharField(max_length=45)
    apellido = models.CharField(max_length=45)
    correo = models.EmailField(unique=True, max_length=100)
    password = models.CharField(max_length=255)
    tipo_documento = models.CharField(max_length=20)
    numero_documento = models.CharField(max_length=10, unique=True)
    foto_perfil = models.FileField(upload_to='profile_photos/', blank=True, null=True)
    rol = models.ForeignKey(Rol, on_delete=models.PROTECT, db_column='rol_id', related_name='usuarios')
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)
    debe_cambiar_password = models.BooleanField(default=False)
    password_temporal = models.BooleanField(default=False)

    class Meta:
        db_table = 'usuario'
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.nombre} {self.apellido}'.strip()


class Administrador(models.Model):
    """Perfil para usuarios con permisos administrativos."""

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, db_column='usuario_id', related_name='administrador_perfil')

    class Meta:
        db_table = 'administrador'
        ordering = ['id']

    def __str__(self) -> str:
        return f'Administrador {self.usuario_id}'


class Notificacion(models.Model):
    """Notificaciones persistentes mostradas dentro del sistema."""

    class Tipo(models.TextChoices):
        INFO = 'info', 'Info'
        EXITO = 'exito', 'Exito'
        ALERTA = 'alerta', 'Alerta'

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, db_column='usuario_id', related_name='notificaciones')
    titulo = models.CharField(max_length=120)
    mensaje = models.TextField()
    url_destino = models.CharField(max_length=255, blank=True, null=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, default=Tipo.INFO)
    leida = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notificacion'
        ordering = ['-creada_en', '-id']

    def __str__(self) -> str:
        return f'Notificacion {self.id} para {self.usuario_id}'
