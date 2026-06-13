from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='instructor',
            name='trimestre',
            field=models.ForeignKey(blank=True, db_column='trimestre_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='instructores_asignados', to='academic.trimestre'),
        ),
    ]
