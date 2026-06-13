from django.test import TestCase
from django.urls import reverse

from apps.paneles.reports import build_rows
from apps.test_support import create_usuario, force_business_login


class DashboardRedirectTests(TestCase):
    def setUp(self):
        self.admin_user = create_usuario(
            rol_nombre='administrador',
            correo='admin@test.com',
            numero_documento='9001',
            nombre='Admin',
        )
        self.aprendiz_user = create_usuario(
            rol_nombre='aprendiz',
            correo='apr@test.com',
            numero_documento='9002',
            nombre='Apr',
        )

    def test_home_redirects_to_logged_user_dashboard(self):
        force_business_login(self.client, self.admin_user)
        response = self.client.get(reverse('dashboards:home'))
        self.assertRedirects(response, reverse('dashboards:panel', args=['administrador']))

    def test_role_mismatch_redirects_to_correct_dashboard(self):
        force_business_login(self.client, self.aprendiz_user)
        response = self.client.get(reverse('dashboards:panel', args=['administrador']))
        self.assertRedirects(response, reverse('dashboards:panel', args=['aprendiz']))


class ReportSearchTests(TestCase):
    def setUp(self):
        create_usuario(
            rol_nombre='aprendiz',
            correo='keiner.real@test.com',
            numero_documento='9101',
            nombre='Keiner',
            apellido='Pedrozo',
        )
        create_usuario(
            rol_nombre='aprendiz',
            correo='rodriguezkeiner434@gmail.com',
            numero_documento='9102',
            nombre='David',
            apellido='Perez',
        )

    def test_text_search_matches_name_without_matching_email_fragment(self):
        _headers, rows = build_rows('usuarios', {'q': 'keiner'})

        self.assertEqual([row[1] for row in rows], ['Keiner'])

    def test_email_search_matches_email_when_address_is_entered(self):
        _headers, rows = build_rows('usuarios', {'q': 'rodriguezkeiner434@gmail.com'})

        self.assertEqual([row[1] for row in rows], ['David'])
