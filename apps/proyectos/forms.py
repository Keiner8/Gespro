"""Formularios del modulo de proyectos, entregables y evaluaciones."""

from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from apps.academico.models import Aprendiz, Instructor, Trimestre

from .models import Entregable, Evaluacion, Proyecto

MAX_EVIDENCE_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_EVIDENCE_EXTENSIONS = {
    '.pdf',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.png',
    '.jpg',
    '.jpeg',
    '.txt',
    '.csv',
}


class DateInput(forms.DateInput):
    input_type = 'date'


class DecimalCommaField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip().replace(',', '.')
        return super().to_python(value)


class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = '__all__'
        widgets = {
            'fecha_inicio': DateInput(),
            'fecha_fin': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gaes'].help_text = 'Selecciona el equipo Scrum responsable del proyecto.'
        self.fields['estado'].help_text = 'Usa un estado claro para el seguimiento del proyecto.'


class EntregableForm(forms.ModelForm):
    url = forms.URLField(
        required=False,
        max_length=200,
        label='Url',
        help_text='Opcional: pega un enlace si la evidencia esta en otro repositorio.',
    )
    archivo_upload = forms.FileField(
        required=False,
        label='Archivo',
        help_text='Adjunta un archivo solo si no usaras enlace externo.',
        widget=forms.FileInput(attrs={'accept': ','.join(sorted(ALLOWED_EVIDENCE_EXTENSIONS))}),
    )

    class Meta:
        model = Entregable
        fields = ['nombre', 'descripcion', 'proyecto', 'trimestre', 'aprendiz', 'fecha_limite', 'url', 'archivo_upload']
        widgets = {
            'fecha_limite': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['aprendiz'].queryset = Aprendiz.objects.select_related('usuario', 'usuario__rol').filter(
            usuario__rol__nombre_rol__iexact='aprendiz',
        ).order_by('usuario__nombre')
        self.fields['proyecto'].label_from_instance = self._proyecto_label
        self.fields['trimestre'].label_from_instance = self._trimestre_label
        self.fields['aprendiz'].label_from_instance = self._aprendiz_label
        self.fields['trimestre'].help_text = 'Relaciona el entregable con el periodo academico correcto.'
        self.fields['proyecto'].help_text = 'Selecciona el proyecto al que corresponde esta evidencia.'
        self.fields['aprendiz'].help_text = 'Selecciona un aprendiz solo si el entregable es individual.'
        self.fields['fecha_limite'].help_text = 'Opcional: si la dejas vacia, la entrega quedara con fecha indefinida.'

    @staticmethod
    def _proyecto_label(proyecto):
        ficha = proyecto.gaes.ficha.codigo_ficha if proyecto.gaes and proyecto.gaes.ficha else 'Sin ficha'
        equipo = proyecto.gaes.nombre if proyecto.gaes else 'Sin Scrum'
        return f'{proyecto.nombre} - {equipo} - {ficha}'

    @staticmethod
    def _trimestre_label(trimestre: Trimestre):
        return str(trimestre)

    @staticmethod
    def _aprendiz_label(aprendiz):
        usuario = aprendiz.usuario
        return f'{usuario.nombre} {usuario.apellido} - {aprendiz.ficha.codigo_ficha}'

    def clean_archivo_upload(self):
        return validate_evidence_file(self.cleaned_data.get('archivo_upload'))


class EntregaEvidenciaForm(forms.Form):
    url = forms.URLField(
        label='Url',
        required=False,
        max_length=200,
        help_text='Opcional: pega un enlace si la evidencia esta en otro repositorio.',
        widget=forms.TextInput(),
    )
    archivo_upload = forms.FileField(
        required=False,
        label='Archivo',
        help_text='Adjunta un archivo solo si no usaras enlace externo.',
        widget=forms.FileInput(attrs={'accept': ','.join(sorted(ALLOWED_EVIDENCE_EXTENSIONS))}),
    )

    def clean_archivo_upload(self):
        return validate_evidence_file(self.cleaned_data.get('archivo_upload'))

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('url') and not cleaned_data.get('archivo_upload'):
            raise forms.ValidationError('Debes adjuntar un archivo o registrar un enlace para entregar la evidencia.')
        return cleaned_data


def validate_evidence_file(uploaded_file):
    if not uploaded_file:
        return uploaded_file
    extension = Path(uploaded_file.name or '').suffix.lower()
    if extension not in ALLOWED_EVIDENCE_EXTENSIONS:
        allowed = ', '.join(sorted(ALLOWED_EVIDENCE_EXTENSIONS))
        raise ValidationError(f'Tipo de archivo no permitido. Usa uno de estos formatos: {allowed}.')
    if uploaded_file.size > MAX_EVIDENCE_FILE_SIZE:
        raise ValidationError('El archivo supera el tamaño máximo permitido de 5 MB.')
    return uploaded_file


class EvaluacionForm(forms.ModelForm):
    calificacion = DecimalCommaField(
        label='Calificacion',
        max_digits=5,
        decimal_places=2,
        widget=forms.TextInput(attrs={'inputmode': 'decimal', 'placeholder': 'Ej: 4,5'}),
    )

    class Meta:
        model = Evaluacion
        fields = ['entregable', 'aprendiz', 'gaes', 'evaluador', 'escala_calificacion', 'calificacion', 'observaciones', 'fecha']
        widgets = {
            'fecha': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['evaluador'].queryset = Instructor.objects.select_related('usuario', 'usuario__rol').filter(
            usuario__rol__nombre_rol__iexact='instructor',
        ).order_by('usuario__nombre')
        self.fields['entregable'].label_from_instance = self._entregable_label
        self.fields['aprendiz'].label_from_instance = self._aprendiz_label
        self.fields['gaes'].label_from_instance = self._gaes_label
        self.fields['evaluador'].label_from_instance = self._instructor_label
        self.fields['aprendiz'].label = 'Aprendiz individual'
        self.fields['gaes'].label = 'Equipo Scrum'
        self.fields['evaluador'].label = 'Instructor evaluador'
        self.fields['escala_calificacion'].label = 'Escala de calificacion'
        self.fields['escala_calificacion'].help_text = 'Elige si la nota sera de 1 a 5, de 1 a 10 o de 1 a 100.'
        self.fields['calificacion'].help_text = 'Registra la nota dentro de la escala seleccionada. Puedes usar coma o punto decimal.'
        self.fields['observaciones'].help_text = 'Describe fortalezas, ajustes o recomendaciones para el entregable.'
        self.fields['aprendiz'].help_text = 'Usa este campo si la calificacion corresponde a un aprendiz puntual.'
        self.fields['gaes'].help_text = 'Usa este campo si la calificacion corresponde al equipo Scrum completo.'
        self.fields['entregable'].help_text = 'Selecciona el entregable que sera evaluado.'

    @staticmethod
    def _aprendiz_label(aprendiz):
        usuario = aprendiz.usuario
        return f'{usuario.nombre} {usuario.apellido} - {aprendiz.ficha.codigo_ficha}'

    @staticmethod
    def _instructor_label(instructor):
        usuario = instructor.usuario
        ficha = instructor.ficha.codigo_ficha if instructor.ficha else 'Sin ficha'
        return f'{usuario.nombre} {usuario.apellido} - {ficha}'

    @staticmethod
    def _gaes_label(gaes):
        return f'{gaes.nombre} - ficha {gaes.ficha.codigo_ficha}'

    @staticmethod
    def _entregable_label(entregable):
        proyecto = entregable.proyecto.nombre if entregable.proyecto else 'Sin proyecto'
        return f'{entregable.nombre} - {proyecto}'

    def clean(self):
        cleaned_data = super().clean()
        entregable = cleaned_data.get('entregable')
        aprendiz = cleaned_data.get('aprendiz')
        gaes = cleaned_data.get('gaes')
        escala = cleaned_data.get('escala_calificacion') or Evaluacion.EscalaCalificacion.UNO_CIEN
        calificacion = cleaned_data.get('calificacion')

        if not aprendiz and not gaes and entregable and entregable.aprendiz:
            cleaned_data['aprendiz'] = entregable.aprendiz
            aprendiz = entregable.aprendiz

        if not gaes and not aprendiz and entregable and entregable.proyecto and entregable.proyecto.gaes:
            cleaned_data['gaes'] = entregable.proyecto.gaes
            gaes = entregable.proyecto.gaes

        if not aprendiz and not gaes:
            raise forms.ValidationError('Debes asociar la calificacion a un aprendiz individual o a un equipo Scrum.')

        if calificacion is not None:
            maximo = int(escala)
            if calificacion < 1 or calificacion > maximo:
                self.add_error('calificacion', f'La calificacion debe estar entre 1 y {maximo}.')

        return cleaned_data
