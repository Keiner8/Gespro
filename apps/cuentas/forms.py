"""Formularios server-side para reemplazar CRUD hechos con JavaScript."""

from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError

from .models import Rol, Usuario
from .services import is_strong_password

MAX_PROFILE_PHOTO_SIZE = 2 * 1024 * 1024
ALLOWED_PROFILE_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def format_person_name(value: str) -> str:
    value = ' '.join((value or '').strip().split())
    return ' '.join(part[:1].upper() + part[1:].lower() for part in value.split(' '))


class LoginForm(forms.Form):
    correo = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={'autocomplete': 'username', 'placeholder': 'usuario@correo.com'}),
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'placeholder': 'Ingresa tu contraseña'}),
    )


class PasswordRecoveryRequestForm(forms.Form):
    correo = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'autocomplete': 'email', 'placeholder': 'usuario@correo.com'}),
    )


class PasswordResetConfirmForm(forms.Form):
    correo = forms.EmailField(widget=forms.HiddenInput)
    codigo = forms.CharField(
        label='Código de recuperación',
        max_length=6,
        help_text='Revisa el código enviado a tu correo.',
        widget=forms.TextInput(
            attrs={
                'inputmode': 'numeric',
                'maxlength': '6',
                'pattern': '[0-9]{6}',
                'placeholder': 'Código de 6 dígitos',
                'title': 'Ingresa el código numérico de 6 dígitos.',
            }
        ),
    )
    nueva_password = forms.CharField(
        label='Nueva contraseña',
        help_text='Debe tener mínimo 8 caracteres, una mayúscula, una minúscula, un número y un símbolo.',
        widget=forms.PasswordInput(
            attrs={
                'autocomplete': 'new-password',
                'placeholder': 'Nueva contraseña',
                'pattern': '(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[^A-Za-z0-9]).{8,}',
                'minlength': '8',
                'title': 'Debe tener mínimo 8 caracteres, una mayúscula, una minúscula, un número y un símbolo.',
            }
        ),
    )
    confirmar_password = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Repite la contraseña'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('nueva_password') != cleaned.get('confirmar_password'):
            self.add_error('confirmar_password', 'Las contraseñas no coinciden.')
        password = cleaned.get('nueva_password', '')
        if password and not is_strong_password(password):
            self.add_error('nueva_password', 'La contraseña debe tener mínimo 8 caracteres, una mayúscula, una minúscula, un número y un símbolo.')
        return cleaned


class RegisterForm(forms.Form):
    TIPO_DOCUMENTO_CHOICES = [
        ('', 'Selecciona tu tipo de documento'),
        ('CC', 'Cédula de ciudadanía'),
        ('TI', 'Tarjeta de identidad'),
        ('CE', 'Cédula de extranjería'),
        ('PA', 'Pasaporte'),
    ]

    nombre = forms.CharField(
        label='Nombre',
        max_length=45,
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Tu nombre',
                'class': 'name-capitalize-input',
                'autocapitalize': 'words',
            }
        ),
    )
    apellido = forms.CharField(
        label='Apellido',
        max_length=45,
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Tu apellido',
                'class': 'name-capitalize-input',
                'autocapitalize': 'words',
            }
        ),
    )
    correo = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'placeholder': 'usuario@correo.com', 'autocomplete': 'email'}),
    )
    tipo_documento = forms.ChoiceField(
        label='Tipo de documento',
        choices=TIPO_DOCUMENTO_CHOICES,
    )
    numero_documento = forms.CharField(
        label='Número de documento',
        max_length=10,
        help_text='',
        widget=forms.TextInput(
            attrs={
                'type': 'tel',
                'inputmode': 'numeric',
                'placeholder': 'Solo números',
                'maxlength': '10',
                'pattern': '[0-9]{6,10}',
                'title': 'Ingresa solo numeros, entre 6 y 10 digitos.',
            }
        ),
    )
    password = forms.CharField(
        label='Contraseña',
        help_text='',
        widget=forms.PasswordInput(
            attrs={
                'autocomplete': 'new-password',
                'placeholder': 'Crea una contraseña segura',
                'pattern': '(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[^A-Za-z0-9]).{8,}',
                'minlength': '8',
            }
        ),
    )
    password_confirm = forms.CharField(
        label='Confirmar contraseña',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Repite la contraseña'}),
    )

    def clean_numero_documento(self):
        value = self.cleaned_data['numero_documento'].strip()
        if not value.isdigit() or not 6 <= len(value) <= 10:
            raise forms.ValidationError('Ingresa un numero de documento valido.')
        return value

    def clean_nombre(self):
        return format_person_name(self.cleaned_data['nombre'])

    def clean_apellido(self):
        return format_person_name(self.cleaned_data['apellido'])

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password', '')
        password_confirm = cleaned.get('password_confirm', '')
        if password and not is_strong_password(password):
            self.add_error('password', 'La contraseña no cumple los requisitos de seguridad.')
        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', 'Las contraseñas no coinciden.')
        return cleaned


class UsuarioForm(forms.ModelForm):
    """CRUD server-side de usuarios para el modulo de administracion."""

    TIPO_DOCUMENTO_CHOICES = RegisterForm.TIPO_DOCUMENTO_CHOICES

    tipo_documento = forms.ChoiceField(
        label='Tipo documento',
        choices=TIPO_DOCUMENTO_CHOICES,
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(render_value=True),
        required=False,
        help_text='Para instructores se puede dejar vacía y el sistema usará una temporal.',
    )

    class Meta:
        model = Usuario
        fields = [
            'nombre',
            'apellido',
            'correo',
            'tipo_documento',
            'numero_documento',
            'rol',
            'estado',
            'password',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rol'].queryset = Rol.objects.order_by('id')
        self.fields['nombre'].widget.attrs.update({'placeholder': 'Nombre del usuario'})
        self.fields['apellido'].widget.attrs.update({'placeholder': 'Apellido del usuario'})
        self.fields['correo'].widget.attrs.update({'placeholder': 'usuario@correo.com'})
        self.fields['numero_documento'].widget.attrs.update(
            {
                'type': 'tel',
                'inputmode': 'numeric',
                'placeholder': 'Solo números',
                'maxlength': '10',
                'pattern': '[0-9]{6,10}',
                'title': 'Ingresa solo números, entre 6 y 10 dígitos.',
            }
        )
        self.fields['estado'].help_text = 'Define si la cuenta puede ingresar al sistema.'
        self.fields['rol'].help_text = 'Selecciona el rol funcional dentro de GESPRO.'

    def clean_numero_documento(self):
        value = self.cleaned_data['numero_documento'].strip()
        if not value.isdigit() or not 6 <= len(value) <= 10:
            raise forms.ValidationError('Ingresa un número de documento válido, entre 6 y 10 dígitos.')
        return value

    def clean_password(self):
        value = self.cleaned_data.get('password', '').strip()
        if value and len(value) < 8:
            raise forms.ValidationError('Si defines una contraseña manual, debe tener al menos 8 caracteres.')
        return value

    def clean_nombre(self):
        return format_person_name(self.cleaned_data['nombre'])

    def clean_apellido(self):
        return format_person_name(self.cleaned_data['apellido'])


class ProfileRequestForm(forms.ModelForm):
    remove_photo = forms.BooleanField(
        required=False,
        label='Quitar foto actual',
    )

    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'correo', 'foto_perfil']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Tu nombre'}),
            'apellido': forms.TextInput(attrs={'placeholder': 'Tu apellido'}),
            'correo': forms.EmailInput(attrs={'placeholder': 'tu-correo@dominio.com', 'autocomplete': 'email'}),
            'foto_perfil': forms.FileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].help_text = 'Actualiza tu nombre visible dentro del sistema.'
        self.fields['apellido'].help_text = 'Actualiza tu apellido visible dentro del sistema.'
        self.fields['correo'].help_text = 'Si cambias este correo, la confirmacion llegara primero al correo actual.'
        self.fields['foto_perfil'].help_text = 'Sube una imagen para tu avatar del sistema.'
        self.fields['foto_perfil'].required = False

    def clean_correo(self):
        return self.cleaned_data['correo'].strip().lower()

    def clean_foto_perfil(self):
        uploaded_file = self.cleaned_data.get('foto_perfil')
        if not uploaded_file:
            return uploaded_file
        extension = Path(uploaded_file.name or '').suffix.lower()
        if extension not in ALLOWED_PROFILE_PHOTO_EXTENSIONS:
            raise ValidationError('Solo se permiten imagenes JPG, PNG o WEBP.')
        if uploaded_file.size > MAX_PROFILE_PHOTO_SIZE:
            raise ValidationError('La foto de perfil supera el tamaño máximo permitido de 2 MB.')
        return uploaded_file

    def clean_nombre(self):
        return format_person_name(self.cleaned_data['nombre'])

    def clean_apellido(self):
        return format_person_name(self.cleaned_data['apellido'])


class ProfileUpdateConfirmForm(forms.Form):
    codigo = forms.CharField(
        label='Código de verificación',
        max_length=6,
        help_text='Ingresa el código enviado al correo actual registrado.',
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'placeholder': 'Código de 6 dígitos'}),
    )
