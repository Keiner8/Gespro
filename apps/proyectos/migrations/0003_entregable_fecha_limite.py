from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_evaluacion_final_trimestre'),
    ]

    operations = [
        migrations.AddField(
            model_name='entregable',
            name='fecha_limite',
            field=models.DateField(blank=True, null=True),
        ),
    ]
