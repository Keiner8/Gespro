"""Formulario del asistente virtual."""

from django import forms


class AssistantPromptForm(forms.Form):
    texto = forms.CharField(
        label='Pregunta',
        help_text='Describe con claridad lo que necesitas consultar o resumir.',
        widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Escribe aqui tu consulta para el asistente...'}),
    )
