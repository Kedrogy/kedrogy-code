from django.db import models


class DjangoDataset(models.Model):
    # column name: dataset_name
    dataset_name = models.CharField(max_length=200)

    # N/A=migrations
    image = models.CharField(max_length=400, default="N/A")
    workingDir = models.CharField(max_length=200, default="N/A")
    pipeline = models.CharField(max_length=200, default="N/A")
    recipe = models.CharField(max_length=200, default="N/A")
    recipe_options = models.CharField(max_length=400, default="N/A")

    def __str__(self):
        return self.dataset_name

    def to_dict(self):
        # print("dataset_id", self.id, flush=True)
        return {
            "dataset_name": self.dataset_name,
            "image": self.image,
            "workingDir": self.workingDir,
            "pipeline": self.pipeline,
            "recipe": self.recipe,
            "recipe_options": self.recipe_options,
            # for tasks
            "dataset_id": self.id,
        }


class DjangoModel(models.Model):
    on_dataset = models.ForeignKey(DjangoDataset, on_delete=models.CASCADE)

    labels = models.CharField(max_length=400, default="N/A")

    # def __str__(self):
    #     return self.dataset_name
