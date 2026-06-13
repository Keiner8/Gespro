from django.urls import path

from .views import assistant_home

app_name = 'assistant'

urlpatterns = [
    path('', assistant_home, name='home'),
]
