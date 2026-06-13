from django.test import TestCase
from django.urls import reverse

from apps.test_support import (
    create_aprendiz,
    create_ficha,
    create_instructor,
    create_usuario,
    force_business_login,
)


class AcademicPermissionsTests(TestCase):
    def setUp(self):
        self.ficha_1 = create_ficha('1001')
        self.ficha_2 = create_ficha('2002')

        self.instructor_user = create_usuario(
            rol_nombre='instructor',
            correo='inst@test.com',
            numero_documento='2001',
            nombre='Ines',
        )
        self.instructor = create_instructor(self.instructor_user, self.ficha_1)

        aprendiz_user_visible = create_usuario(
            rol_nombre='aprendiz',
            correo='apr1@test.com',
            numero_documento='3001',
            nombre='Laura',
        )
        aprendiz_user_hidden = create_usuario(
            rol_nombre='aprendiz',
            correo='apr2@test.com',
            numero_documento='3002',
            nombre='Pedro',
        )
        self.aprendiz_visible = create_aprendiz(aprendiz_user_visible, self.ficha_1)
        self.aprendiz_hidden = create_aprendiz(aprendiz_user_hidden, self.ficha_2)

    def test_instructor_only_sees_assigned_ficha(self):
        force_business_login(self.client, self.instructor_user)
        response = self.client.get(reverse('academic:ficha_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ficha_1.codigo_ficha)
        self.assertNotContains(response, self.ficha_2.codigo_ficha)

    def test_instructor_only_sees_aprendices_from_own_ficha(self):
        force_business_login(self.client, self.instructor_user)
        response = self.client.get(reverse('academic:aprendiz_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.aprendiz_visible.usuario.correo)
        self.assertNotContains(response, self.aprendiz_hidden.usuario.correo)
