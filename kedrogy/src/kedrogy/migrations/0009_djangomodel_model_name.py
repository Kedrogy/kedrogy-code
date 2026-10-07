from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kedrogy", "0008_djangodataset_data_table_name_djangodataset_id_field_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="djangomodel",
            name="model_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
