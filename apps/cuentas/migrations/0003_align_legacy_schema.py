# Legacy schema alignment kept as a no-op after moving the project to PostgreSQL.

from django.db import migrations


def align_legacy_schema(apps, schema_editor):
    return


def noop_reverse(apps, schema_editor):
    """No-op reverse: this migration only normalizes legacy schema."""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('accounts', '0002_notificacion'),
    ]

    operations = [
        migrations.RunPython(align_legacy_schema, noop_reverse),
    ]
