"""Formularios del modulo academico.

Aqui se migra a Django puro:
- fichas
- trimestres
- equipos Scrum (tabla gaes)
- perfiles de aprendices
- perfiles de instructores
"""

from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.cuentas.models import Usuario
from apps.proyectos.models import EvaluacionFinalTrimestre

from .models import Aprendiz, Ficha, Gaes, Instructor, Trimestre

MAX_CSV_FILE_SIZE = 2 * 1024 * 1024


def validate_csv_file(uploaded_file):
    if not uploaded_file:
        return uploaded_file
    if Path(uploaded_file.name or '').suffix.lower() != '.csv':
        raise ValidationError('Solo se permiten archivos CSV.')
    if uploaded_file.size > MAX_CSV_FILE_SIZE:
        raise ValidationError('El archivo CSV supera el tamaño máximo permitido de 2 MB.')
    return uploaded_file


class DateInput(forms.DateInput):
    input_type = 'date'


class TrimestreSelect(forms.Select):
    def __init__(self, *args, trimestre_meta=None, **kwargs):
        self.trimestre_meta = trimestre_meta or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        raw_value = getattr(value, 'value', value)
        meta = self.trimestre_meta.get(str(raw_value))
        if meta:
            option['attrs']['data-ficha-id'] = str(meta['ficha_id'])
            option['attrs']['data-disponible'] = 'true' if meta['disponible'] else 'false'
            if not meta['disponible']:
                option['attrs']['disabled'] = True
        return option


class TrimestreChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, trimestre):
        disponibilidad = 'Disponible' if getattr(trimestre, 'disponible', True) else 'No disponible'
        return f'{trimestre} - {disponibilidad}'


class FichaForm(forms.ModelForm):
    class Meta:
        model = Ficha
        fields = '__all__'
        widgets = {
            'fecha_inicio': DateInput(),
            'fecha_fin': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codigo_ficha'].help_text = 'Usa el codigo oficial de la ficha.'
        self.fields['programa_formacion'].help_text = 'Nombre completo del programa de formacion.'


class TrimestreForm(forms.ModelForm):
    class Meta:
        model = Trimestre
        fields = '__all__'
        widgets = {
            'fecha_inicio': DateInput(),
            'fecha_fin': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['numero'].help_text = 'Numero consecutivo dentro de la ficha seleccionada.'

    def clean(self):
        cleaned_data = super().clean()
        numero = cleaned_data.get('numero')
        ficha = cleaned_data.get('ficha')
        if numero and ficha:
            maximo = 7 if ficha.nivel == Ficha.Nivel.TECNOLOGO else 4
            if numero > maximo:
                self.add_error('numero', f'Esta ficha permite maximo {maximo} trimestres segun su nivel de formacion.')
        return cleaned_data


class GaesForm(forms.ModelForm):
    class Meta:
        model = Gaes
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].help_text = 'Nombre identificador del equipo Scrum.'


class AprendizForm(forms.ModelForm):
    class Meta:
        model = Aprendiz
        fields = ['usuario', 'ficha']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = Usuario.objects.select_related('rol').filter(rol__nombre_rol__iexact='aprendiz').order_by('nombre', 'apellido')
        self.fields['ficha'].queryset = Ficha.objects.order_by('codigo_ficha')
        self.fields['ficha'].widget.attrs['data-ficha-filter'] = 'true'
        self.fields['usuario'].help_text = 'Selecciona un usuario con rol aprendiz.'
        self.fields['ficha'].help_text = 'Asocia el aprendiz a su ficha academica.'


class InstructorForm(forms.ModelForm):
    class Meta:
        model = Instructor
        fields = ['usuario', 'ficha', 'trimestre', 'especialidad']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usuario'].queryset = Usuario.objects.select_related('rol').filter(rol__nombre_rol__iexact='instructor').order_by('nombre', 'apellido')
        self.fields['ficha'].queryset = Ficha.objects.order_by('codigo_ficha')
        self.fields['ficha'].widget.attrs['data-ficha-filter'] = 'true'
        trimestre_actual_id = self.instance.trimestre_id if self.instance and self.instance.pk else None
        trimestres = list(
            Trimestre.objects.select_related('ficha')
            .annotate(
                tiene_cierre=Exists(
                    EvaluacionFinalTrimestre.objects.filter(trimestre_id=OuterRef('pk'))
                )
            )
            .order_by('ficha__codigo_ficha', 'numero')
        )
        trimestre_meta = {}
        for trimestre in trimestres:
            bloqueado = (
                trimestre.estado == Trimestre.Estado.FINALIZADO
                or trimestre.fecha_fin < timezone.localdate()
                or trimestre.tiene_cierre
            )
            trimestre.disponible = not bloqueado or trimestre.id == trimestre_actual_id
            trimestre_meta[str(trimestre.id)] = {
                'ficha_id': trimestre.ficha_id,
                'disponible': trimestre.disponible,
            }
        self.fields['trimestre'] = TrimestreChoiceField(
            label='Trimestre',
            queryset=Trimestre.objects.filter(id__in=[trimestre.id for trimestre in trimestres]),
            required=False,
            help_text='Selecciona un trimestre disponible de la ficha asignada.',
            widget=TrimestreSelect(attrs={'data-trimestre-filter': 'true'}, trimestre_meta=trimestre_meta),
        )
        self.fields['trimestre'].choices = [('', '---------')] + [
            (trimestre.id, self.fields['trimestre'].label_from_instance(trimestre))
            for trimestre in trimestres
        ]
        self.fields['usuario'].help_text = 'Selecciona un usuario con rol instructor.'
        self.fields['ficha'].help_text = 'Ficha principal que tendra asignada el instructor.'
        self.fields['especialidad'].help_text = 'Area o especialidad del instructor.'

    def clean(self):
        cleaned_data = super().clean()
        ficha = cleaned_data.get('ficha')
        trimestre = cleaned_data.get('trimestre')
        if ficha and trimestre and trimestre.ficha_id != ficha.id:
            self.add_error('trimestre', 'El trimestre seleccionado debe pertenecer a la ficha asignada.')
        trimestre_actual_id = self.instance.trimestre_id if self.instance and self.instance.pk else None
        if trimestre and trimestre.id != trimestre_actual_id:
            bloqueado = (
                trimestre.estado == Trimestre.Estado.FINALIZADO
                or trimestre.fecha_fin < timezone.localdate()
                or EvaluacionFinalTrimestre.objects.filter(trimestre=trimestre).exists()
            )
            if bloqueado:
                self.add_error('trimestre', 'Este trimestre ya finalizo o fue calificado y no se puede asignar nuevamente.')
        return cleaned_data


class BulkAprendizUploadForm(forms.Form):
    ficha = forms.ModelChoiceField(
        label='Ficha de los aprendices',
        queryset=Ficha.objects.order_by('codigo_ficha'),
        help_text='Selecciona la ficha a la que pertenecerán todos los aprendices del archivo.',
        widget=forms.Select(attrs={'data-ficha-filter': 'true'}),
    )
    archivo = forms.FileField(
        label='Archivo CSV',
        help_text='Columnas: nombre, apellido, correo, tipo_documento, numero_documento',
        widget=forms.FileInput(attrs={'accept': '.csv'}),
    )

    def clean_archivo(self):
        return validate_csv_file(self.cleaned_data.get('archivo'))


class BulkInstructorUploadForm(forms.Form):
    archivo = forms.FileField(
        label='Archivo CSV',
        help_text='Columnas: nombre, apellido, correo, tipo_documento, numero_documento, ficha_codigo, trimestre_numero, especialidad',
        widget=forms.FileInput(attrs={'accept': '.csv'}),
    )

    def clean_archivo(self):
        return validate_csv_file(self.cleaned_data.get('archivo'))
