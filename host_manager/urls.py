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
from django.conf.urls import url
from . import views

urlpatterns = [
    url(r'^host/$', views.HostViewSet.as_list()),
    url(r'^host/(?P<pk>[\w\-]+)/$', views.HostViewSet.as_detail()),
    url(r'^host/(?P<pk>[\w\-]+)/action/$', views.HostActionView.as_view()),
    url(r'^host/(?P<uuid>[\w\-]+)/xml/$', views.DomainsXmlView.as_view()),
    url(r'^host/(?P<pk>[\w\-]+)/attach_disk/$', views.AttachDiskView.as_view()),
    url(r'^host/(?P<pk>[\w\-]+)/disk/(?P<disk_id>[\w\-]+)/detach/$', views.DetachDiskView.as_view()),
    url(r'^host/(?P<pk>[\w\-]+)/disk/(?P<disk_id>[\w\-]+)/save/$', views.SaveDiskView.as_view()),
    url(r'^host/(?P<host_id>[\w\-]+)/snapshot/$', views.SnapshotViewSet.as_list()),
    url(r'^host/(?P<host_id>[\w\-]+)/snapshot/(?P<pk>[\w\-]+)/$', views.SnapshotViewSet.as_detail()),
    url(r'^host/(?P<host_id>[\w\-]+)/snapshot/(?P<pk>[\w\-]+)/revert/$', views.SnapshotRevertView.as_view()),
    url(r'^overview/$', views.OverviewView.as_view()),
    url(r'^base_disks/$', views.BaseDisksView.as_view()),
    url(r'^networks/$', views.NetworksView.as_view()),
    url(r'^iso/$', views.IsoView.as_view()),
]
