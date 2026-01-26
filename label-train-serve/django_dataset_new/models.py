from django.db import models


class DjangoDataset(models.Model):
    # column name: dataset_name
    dataset_name = models.CharField(max_length=200)

    def __str__(self):
        return self.dataset_name
