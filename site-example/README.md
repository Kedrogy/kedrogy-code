#

## build image

In uv workspace root directory `code` run

```sh
docker build --platform linux/amd64 -t ???/tools .
```

```sh
# while true due to django making many requests
while true ; do kubectl port-forward -n annotate service/postgres-rw 5555:5432 ; done

export $(cat tools/.env)

docker run --platform linux/amd64 --rm -it \
-e PGHOST=host.docker.internal \
-e PGPORT=5555 \
-e PGUSER=postgres \
-e PGDATABASE=annotate \
-e PGPASSWORD=$PGPASSWORD \
-p 8888:8000 \
???/tools
```

## development / admin

Ensure Postgres.app has

```sh
create database stertell_anomalies;
#and stertell_anomalies has
create schema django_schema;
```

and "create superuser" see below.

XXX

```sh
#ensure lb then
ssh -NL5555:localhost:5555 stertell-ai
```

Then can use both manage.py and https://docs.djangoproject.com/en/6.0/ref/django-admin/

```sh
# to run against Postgres.app
export $(cat ../.env-dev)

python -m django migrate --settings mysite.settings
# run django-tasks db_worker
python -m django db_worker --settings mysite.settings

python -m django runserver --settings mysite.settings
```

or

```sh
python -m uvicorn mysite.asgi:application
```

NB:

```sh
python -m django collectstatic --noinput --settings mysite.settings
```

## using shell

```sh
> python mysite/manage.py shell
13 objects imported automatically (use -v 2 for details).

Python 3.12.12 (main, Oct 28 2025, 11:52:25) [Clang 20.1.4 ] on darwin
Type "help", "copyright", "credits" or "license" for more information.
(InteractiveConsole)
>>> DjangoDataset.objects.all()
<QuerySet []>
>>> d = DjangoDataset(dataset_name='foo')
>>> d.save()
>>> d.id
1
>>> DjangoDataset.objects.all()
<QuerySet [<DjangoDataset: DjangoDataset object (1)>]>
>>>
```

## create superuser

to delete superuser drop record in `django_schema.auth_user`

```sh
export $(cat ../.env-dev)
DJANGO_SUPERUSER_EMAIL=team@ysz.vc DJANGO_SUPERUSER_USERNAME=superuser python -m django createsuperuser --no-input --settings mysite.settings
```

## make migrations

```sh
> python -m django makemigrations --settings mysite.settings django_dataset_new
Migrations for 'django_dataset_new':
  /Users/me/stertell-ai/all-in-one/code/django-dataset-new/django_dataset_new/migrations/0001_initial.py
    + Create model DjangoDataset
```
