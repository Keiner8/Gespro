from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0002_instructor_trimestre'),
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EvaluacionFinalTrimestre',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(choices=[('aprobado', 'Aprobado'), ('no_aprobado', 'No aprobado')], max_length=20)),
                ('observaciones', models.TextField(blank=True, null=True)),
                ('fecha', models.DateTimeField(auto_now=True)),
                ('aprendiz', models.ForeignKey(db_column='aprendiz_id', on_delete=django.db.models.deletion.CASCADE, related_name='evaluaciones_finales', to='academic.aprendiz')),
                ('instructor', models.ForeignKey(db_column='instructor_id', on_delete=django.db.models.deletion.CASCADE, related_name='evaluaciones_finales', to='academic.instructor')),
                ('trimestre', models.ForeignKey(db_column='trimestre_id', on_delete=django.db.models.deletion.CASCADE, related_name='evaluaciones_finales', to='academic.trimestre')),
            ],
            options={
                'db_table': 'evaluacion_final_trimestre',
                'ordering': ['trimestre_id', 'aprendiz_id'],
                'unique_together': {('aprendiz', 'trimestre')},
            },
        ),
    ]
