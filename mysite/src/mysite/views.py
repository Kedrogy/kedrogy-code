from django.http import HttpResponse


def logout(request):
    return HttpResponse("You've been logged out.")
