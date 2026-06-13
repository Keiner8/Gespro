"""Modelos del dominio de proyectos, entregables y evaluacion."""

from django.db import models


class Proyecto(models.Model):
    class Estado(models.TextChoices):
        EN_PROCESO = 'en_proceso', 'En proceso'
        FINALIZADO = 'finalizado', 'Finalizado'
        CANCELADO = 'cancelado', 'Cancelado'

    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    gaes = models.ForeignKey('academic.Gaes', on_delete=models.CASCADE, db_column='gaes_id', related_name='proyectos')
    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin = models.DateField(blank=True, null=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.EN_PROCESO)

    class Meta:
        db_table = 'proyecto'
        ordering = ['id']

    def __str__(self) -> str:
        return self.nombre


class Entregable(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, db_column='proyecto_id', related_name='entregables')
    trimestre = models.ForeignKey('academic.Trimestre', on_delete=models.CASCADE, db_column='trimestre_id', related_name='entregables')
    aprendiz = models.ForeignKey('academic.Aprendiz', on_delete=models.SET_NULL, db_column='aprendiz_id', related_name='entregables', null=True, blank=True)
    fecha_limite = models.DateField(blank=True, null=True)
    url = models.CharField(max_length=200, blank=True, null=True)
    archivo = models.BinaryField(blank=True, null=True)
    nombre_archivo = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'entregable'
        ordering = ['id']

    def __str__(self) -> str:
        return self.nombre


class ProyectoEntregable(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, db_column='proyecto_id')
    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, db_column='entregable_id')

    class Meta:
        db_table = 'proyecto_entregable'
        ordering = ['id']


class Evaluacion(models.Model):
    class EscalaCalificacion(models.TextChoices):
        UNO_CINCO = '5', '1 a 5'
        UNO_DIEZ = '10', '1 a 10'
        UNO_CIEN = '100', '1 a 100'

    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, db_column='entregable_id', related_name='evaluaciones')
    aprendiz = models.ForeignKey('academic.Aprendiz', on_delete=models.SET_NULL, db_column='aprendiz_id', related_name='evaluaciones', null=True, blank=True)
    gaes = models.ForeignKey('academic.Gaes', on_delete=models.SET_NULL, db_column='gaes_id', related_name='evaluaciones', null=True, blank=True)
    evaluador = models.ForeignKey('academic.Instructor', on_delete=models.CASCADE, db_column='evaluador_id', related_name='evaluaciones_realizadas')
    escala_calificacion = models.CharField(max_length=3, choices=EscalaCalificacion.choices, default=EscalaCalificacion.UNO_CIEN)
    calificacion = models.DecimalField(max_digits=5, decimal_places=2)
    observaciones = models.TextField(blank=True, null=True)
    fecha = models.DateField()

    class Meta:
        db_table = 'evaluacion'
        ordering = ['-id']

    def __str__(self) -> str:
        return f'Evaluacion {self.id}'


class EvaluacionFinalTrimestre(models.Model):
    class Estado(models.TextChoices):
        APROBADO = 'aprobado', 'Aprobado'
        NO_APROBADO = 'no_aprobado', 'No aprobado'

    aprendiz = models.ForeignKey('academic.Aprendiz', on_delete=models.CASCADE, db_column='aprendiz_id', related_name='evaluaciones_finales')
    instructor = models.ForeignKey('academic.Instructor', on_delete=models.CASCADE, db_column='instructor_id', related_name='evaluaciones_finales')
    trimestre = models.ForeignKey('academic.Trimestre', on_delete=models.CASCADE, db_column='trimestre_id', related_name='evaluaciones_finales')
    estado = models.CharField(max_length=20, choices=Estado.choices)
    observaciones = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'evaluacion_final_trimestre'
        ordering = ['trimestre_id', 'aprendiz_id']
        unique_together = ('aprendiz', 'trimestre')

    def __str__(self) -> str:
        return f'{self.aprendiz_id} - {self.trimestre_id} - {self.estado}'
