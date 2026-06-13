"""Modelos academicos: fichas, personas de formacion y equipos."""

from django.core.exceptions import ValidationError
from django.db import models


class Ficha(models.Model):
    class Nivel(models.TextChoices):
        TECNICO = 'tecnico', 'Tecnico'
        TECNOLOGO = 'tecnologo', 'Tecnologo'

    class Jornada(models.TextChoices):
        MANANA = 'mañana', 'Manana'
        TARDE = 'tarde', 'Tarde'
        NOCHE = 'noche', 'Noche'
        MIXTA = 'mixta', 'Mixta'

    class Modalidad(models.TextChoices):
        PRESENCIAL = 'presencial', 'Presencial'
        VIRTUAL = 'virtual', 'Virtual'
        MIXTA = 'mixta', 'Mixta'

    class Estado(models.TextChoices):
        ACTIVA = 'activa', 'Activa'
        INACTIVA = 'inactiva', 'Inactiva'

    codigo_ficha = models.CharField(max_length=20, unique=True)
    programa_formacion = models.CharField(max_length=100)
    nivel = models.CharField(max_length=20, choices=Nivel.choices, default=Nivel.TECNICO)
    jornada = models.CharField(max_length=20, choices=Jornada.choices)
    modalidad = models.CharField(max_length=20, choices=Modalidad.choices)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVA)

    class Meta:
        db_table = 'ficha'
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.codigo_ficha} - {self.programa_formacion}'


class Aprendiz(models.Model):
    usuario = models.ForeignKey('accounts.Usuario', on_delete=models.CASCADE, db_column='usuario_id', related_name='aprendiz_perfiles')
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, db_column='ficha_id', related_name='aprendices')

    class Meta:
        db_table = 'aprendiz'
        ordering = ['id']

    def __str__(self) -> str:
        return f'Aprendiz {self.usuario_id}'


class Instructor(models.Model):
    usuario = models.ForeignKey('accounts.Usuario', on_delete=models.CASCADE, db_column='usuario_id', related_name='instructor_perfiles')
    ficha = models.ForeignKey(Ficha, on_delete=models.SET_NULL, db_column='ficha_id', related_name='instructores', null=True, blank=True)
    trimestre = models.ForeignKey('Trimestre', on_delete=models.SET_NULL, db_column='trimestre_id', related_name='instructores_asignados', null=True, blank=True)
    especialidad = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = 'instructor'
        ordering = ['id']

    def __str__(self) -> str:
        return f'Instructor {self.usuario_id}'


class Trimestre(models.Model):
    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        FINALIZADO = 'finalizado', 'Finalizado'
        PENDIENTE = 'pendiente', 'Pendiente'

    numero = models.PositiveIntegerField()
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, db_column='ficha_id', related_name='trimestres')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)

    class Meta:
        db_table = 'trimestre'
        ordering = ['ficha_id', 'numero']
        unique_together = ('ficha', 'numero')

    def __str__(self) -> str:
        ficha = self.ficha.codigo_ficha if self.ficha_id else 'Sin ficha'
        return f'Trimestre {self.numero} - {ficha}'

    def clean(self):
        super().clean()
        if self.numero and self.ficha_id:
            maximo = 7 if self.ficha.nivel == Ficha.Nivel.TECNOLOGO else 4
            if self.numero > maximo:
                raise ValidationError({'numero': f'Esta ficha permite maximo {maximo} trimestres segun su nivel de formacion.'})
            duplicado = Trimestre.objects.filter(ficha_id=self.ficha_id, numero=self.numero)
            if self.pk:
                duplicado = duplicado.exclude(pk=self.pk)
            if duplicado.exists():
                raise ValidationError({'numero': 'Este trimestre ya existe para la ficha seleccionada.'})


class Gaes(models.Model):
    """Se mantiene el nombre de tabla para compatibilidad con la base actual."""

    nombre = models.CharField(max_length=100)
    ficha = models.ForeignKey(Ficha, on_delete=models.CASCADE, db_column='ficha_id', related_name='gaes')

    class Meta:
        db_table = 'gaes'
        ordering = ['id']

    def __str__(self) -> str:
        return self.nombre


class AprendizGaes(models.Model):
    aprendiz = models.ForeignKey(Aprendiz, on_delete=models.CASCADE, db_column='aprendiz_id', related_name='gaes_links')
    gaes = models.ForeignKey(Gaes, on_delete=models.CASCADE, db_column='gaes_id', related_name='aprendiz_links')

    class Meta:
        db_table = 'aprendiz_gaes'
        ordering = ['id']
