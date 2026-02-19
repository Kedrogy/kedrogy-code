##kedrogy

## how to generate translations

to create folder "locale" with files django.po run
```sh
django-admin makemessages -l ru --settings=mysite.settings 
```

to create django.mo with translations run
```sh
django-admin compilemessages --settings=mysite.settings
```

FIXME run to move folder "locale" to the right directory (run from kedrogy directory)
```sh
mv ../mysite/src/kedrogy/locale/ src/kedrogy
```

edit file django.po to add more translations