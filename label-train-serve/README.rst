============
django-dataset-new
============

django-dataset-new is a Django app to conduct web-based dataset_new. For each
question, visitors can choose between a fixed number of answers.

Detailed documentation is in the "docs" directory.

Quick start
-----------

1. Add "dataset_new" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...,
        "django_dataset_new",
    ]

2. Include the dataset_new URLconf in your project urls.py like this::

    path("dataset_new/", include("django_dataset_new.urls")),

3. Run ``python manage.py migrate`` to create the models.

4. Start the development server and visit the admin to create a poll.

5. Visit the ``/dataset_new/`` URL to participate in the poll.