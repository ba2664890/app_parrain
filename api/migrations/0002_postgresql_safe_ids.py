import api.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="etudiant",
            name="id",
            field=models.CharField(
                default=api.models.generate_id,
                max_length=36,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="evenement",
            name="id",
            field=models.CharField(
                default=api.models.generate_id,
                max_length=36,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="jeton",
            name="id",
            field=models.CharField(
                default=api.models.generate_id,
                max_length=36,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="journalaudit",
            name="id",
            field=models.CharField(
                default=api.models.generate_id,
                max_length=36,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="parrainage",
            name="id",
            field=models.CharField(
                default=api.models.generate_id,
                max_length=36,
                primary_key=True,
                serialize=False,
            ),
        ),
    ]