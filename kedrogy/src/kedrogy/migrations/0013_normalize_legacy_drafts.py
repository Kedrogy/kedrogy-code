"""Normalize legacy classes in a separate transaction from schema changes."""

import unicodedata
from django.db import migrations


def migrate_drafts(apps, schema_editor):
    """Keep historical identities unresolved until external evidence is checked."""
    Model = apps.get_model("kedrogy", "DjangoModel")
    for model in Model.objects.filter(label_schema__isnull=True).iterator():
        parts = model.labels.split(",")
        labels = [part.strip() for part in parts]
        if (1 <= len(labels) <= 100 and len(set(labels)) == len(labels)
                and all(label and len(label) <= 100 and label != "OTHER" and not label.startswith("-") for label in labels)
                and not any(unicodedata.category(c).startswith("C") for c in model.labels)):
            Model.objects.filter(pk=model.pk).update(label_schema=labels)
    Model.objects.filter(current_serving__isnull=True).update(served=False)


class Migration(migrations.Migration):
    dependencies = [("kedrogy", "0012_alter_djangodataset_prodigy_dataset_id_and_more")]
    operations = [migrations.RunPython(migrate_drafts, migrations.RunPython.noop)]
