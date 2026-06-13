from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import Notificacion
from apps.proyectos.models import Entregable, Evaluacion, Proyecto
from apps.test_support import (
    create_aprendiz,
    create_ficha,
    create_gaes,
    create_instructor,
    create_trimestre,
    create_usuario,
    force_business_login,
)


class ProjectPermissionsAndNotificationsTests(TestCase):
    def setUp(self):
        self.ficha = create_ficha('3003')
        self.trimestre = create_trimestre(self.ficha)
        self.gaes = create_gaes(self.ficha, 'Equipo Alfa')
        self.other_ficha = create_ficha('4004')
        self.other_trimestre = create_trimestre(self.other_ficha)
        self.other_gaes = create_gaes(self.other_ficha, 'Equipo Beta')

        self.instructor_user = create_usuario(
            rol_nombre='instructor',
            correo='instructor@test.com',
            numero_documento='4001',
            nombre='Iris',
        )
        self.instructor = create_instructor(self.instructor_user, self.ficha)

        self.aprendiz_user = create_usuario(
            rol_nombre='aprendiz',
            correo='aprendiz@test.com',
            numero_documento='5001',
            nombre='Mario',
        )
        self.aprendiz = create_aprendiz(self.aprendiz_user, self.ficha, self.gaes)

        other_aprendiz_user = create_usuario(
            rol_nombre='aprendiz',
            correo='otro@test.com',
            numero_documento='5002',
            nombre='Nora',
        )
        self.other_aprendiz = create_aprendiz(other_aprendiz_user, self.other_ficha, self.other_gaes)

        self.proyecto = Proyecto.objects.create(
            nombre='Proyecto Alfa',
            descripcion='Demo',
            gaes=self.gaes,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 1),
            estado=Proyecto.Estado.EN_PROCESO,
        )
        self.other_proyecto = Proyecto.objects.create(
            nombre='Proyecto Beta',
            descripcion='Oculto',
            gaes=self.other_gaes,
            fecha_inicio=date(2026, 1, 1),
            fecha_fin=date(2026, 6, 1),
            estado=Proyecto.Estado.EN_PROCESO,
        )

    def test_aprendiz_only_sees_own_projects(self):
        force_business_login(self.client, self.aprendiz_user)
        response = self.client.get(reverse('projects:proyecto_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.proyecto.nombre)
        self.assertNotContains(response, self.other_proyecto.nombre)

    def test_entregable_creation_creates_notification_for_aprendiz(self):
        force_business_login(self.client, self.instructor_user)
        response = self.client.post(
            f"{reverse('projects:entregable_create')}?ficha={self.ficha.id}&gaes={self.gaes.id}&destino=aprendiz",
            {
                'nombre': 'Entrega 1',
                'descripcion': 'Primera entrega',
                'proyecto': self.proyecto.id,
                'trimestre': self.trimestre.id,
                'aprendiz': self.aprendiz.id,
                'url': 'https://example.com/entrega',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Entregable.objects.filter(nombre='Entrega 1').exists())
        self.assertTrue(Notificacion.objects.filter(usuario=self.aprendiz_user, titulo__icontains='Entregable').exists())

    def test_evaluacion_creation_creates_notification_for_aprendiz(self):
        entregable = Entregable.objects.create(
            nombre='Entrega Eval',
            descripcion='Evaluable',
            proyecto=self.proyecto,
            trimestre=self.trimestre,
            aprendiz=self.aprendiz,
            url='https://example.com/evaluable',
        )
        force_business_login(self.client, self.instructor_user)
        response = self.client.post(
            f"{reverse('projects:evaluacion_create')}?ficha={self.ficha.id}&gaes={self.gaes.id}",
            {
                'entregable': entregable.id,
                'aprendiz': self.aprendiz.id,
                'gaes': self.gaes.id,
                'evaluador': self.instructor.id,
                'escala_calificacion': '100',
                'calificacion': '95.00',
                'observaciones': 'Muy bien',
                'fecha': '2026-05-06',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Evaluacion.objects.filter(entregable=entregable).exists())
        self.assertTrue(Notificacion.objects.filter(usuario=self.aprendiz_user, titulo__icontains='Evaluacion').exists())

    def test_calificacion_respects_selected_scale(self):
        entregable = Entregable.objects.create(
            nombre='Entrega escala',
            descripcion='Evaluable',
            proyecto=self.proyecto,
            trimestre=self.trimestre,
            aprendiz=self.aprendiz,
            url='https://example.com/escala',
        )
        force_business_login(self.client, self.instructor_user)
        response = self.client.post(
            f"{reverse('projects:evaluacion_create')}?ficha={self.ficha.id}&gaes={self.gaes.id}",
            {
                'entregable': entregable.id,
                'aprendiz': self.aprendiz.id,
                'gaes': self.gaes.id,
                'evaluador': self.instructor.id,
                'escala_calificacion': '5',
                'calificacion': '6.00',
                'observaciones': 'Fuera de escala',
                'fecha': '2026-05-06',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'calificacion', 'La calificacion debe estar entre 1 y 5.')

    def test_calificacion_accepts_comma_decimal(self):
        entregable = Entregable.objects.create(
            nombre='Entrega decimal',
            descripcion='Evaluable',
            proyecto=self.proyecto,
            trimestre=self.trimestre,
            aprendiz=self.aprendiz,
            url='https://example.com/decimal',
        )
        force_business_login(self.client, self.instructor_user)
        response = self.client.post(
            f"{reverse('projects:evaluacion_create')}?ficha={self.ficha.id}&gaes={self.gaes.id}",
            {
                'entregable': entregable.id,
                'aprendiz': self.aprendiz.id,
                'gaes': self.gaes.id,
                'evaluador': self.instructor.id,
                'escala_calificacion': '5',
                'calificacion': '1,5',
                'observaciones': 'Decimal con coma',
                'fecha': '2026-05-06',
            },
        )

        self.assertEqual(response.status_code, 302)
        evaluacion = Evaluacion.objects.get(entregable=entregable)
        self.assertEqual(str(evaluacion.calificacion), '1.50')
        self.assertEqual(evaluacion.escala_calificacion, '5')

    def test_entregable_open_shows_preview_and_inline_file(self):
        entregable = Entregable.objects.create(
            nombre='Imagen entregable',
            descripcion='Vista previa',
            proyecto=self.proyecto,
            trimestre=self.trimestre,
            aprendiz=self.aprendiz,
            archivo=b'fake-image',
            nombre_archivo='evidencia.jpg',
        )
        force_business_login(self.client, self.instructor_user)
        response = self.client.get(reverse('projects:entregable_open', args=[entregable.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vista previa de entregable')
        inline_response = self.client.get(reverse('projects:entregable_inline', args=[entregable.id]))
        self.assertEqual(inline_response.status_code, 200)
        self.assertEqual(inline_response['Content-Type'], 'image/jpeg')
        self.assertIn('inline', inline_response['Content-Disposition'])
