from django.http import HttpResponse
from django.utils.translation import gettext as _


def logout(request):
    return HttpResponse("You've been logged out.")
