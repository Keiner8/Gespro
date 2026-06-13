from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import Notificacion
from apps.test_support import create_usuario, force_business_login


class NotificationsViewTests(TestCase):
    def setUp(self):
        self.usuario = create_usuario(
            rol_nombre='aprendiz',
            correo='aprendiz@test.com',
            numero_documento='1001',
            nombre='Ana',
        )
        self.notificacion = Notificacion.objects.create(
            usuario=self.usuario,
            titulo='Prueba',
            mensaje='Mensaje de prueba',
            tipo=Notificacion.Tipo.INFO,
        )

    def test_notifications_list_requires_login(self):
        response = self.client.get(reverse('accounts:notificaciones_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_mark_notification_as_read(self):
        force_business_login(self.client, self.usuario)
        response = self.client.post(reverse('accounts:notificacion_mark_read', args=[self.notificacion.id]))
        self.assertEqual(response.status_code, 302)
        self.notificacion.refresh_from_db()
        self.assertTrue(self.notificacion.leida)
