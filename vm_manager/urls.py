"""vm_manager URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from rest_framework_swagger.views import get_swagger_view

from common.views import ms_static_serve

schema_view = get_swagger_view(title='Keystone API')

urlpatterns = [
    url(r'^static/(?P<path>.*)$', ms_static_serve),
    url(r'^docs/$', schema_view),
    url(r'^user/', include('user_manager.urls')),
    url(r'^host/', include('host_manager.urls')),
]
