from rest_framework import serializers
from .models import DjangoDataset, DjangoModel, DjangoLastDataset


class DjangoDatasetSerializer(serializers.ModelSerializer):
    labelled = serializers.SerializerMethodField()

    class Meta:
        model = DjangoDataset
        fields = [
            "id",
            "dataset_name",
            "image",
            "workingDir",
            "pipeline",
            "recipe_options",
            "data_table_name",
            "id_field",
            "labelled",
        ]

    def get_labelled(self, obj):
        return DjangoLastDataset.objects.filter(dataset_id=obj.id).exists()


class DjangoModelSerializer(serializers.ModelSerializer):
    dataset_name = serializers.CharField(
        source="on_dataset.dataset_name", read_only=True
    )

    class Meta:
        model = DjangoModel
        fields = [
            "id",
            "on_dataset",
            "dataset_name",
            "labels",
            "a_preprocess_fun",
            "trained",
            "served",
        ]
        read_only_fields = ["trained", "served"]
