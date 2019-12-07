# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.apps import AppConfig

from django.db.models.signals import post_migrate


def init_user(*args, **kwargs):
    from django.contrib.auth.models import User

    if not User.objects.all().exists():
        user = User()
        user.username = 'root'
        user.email = 'root@xxx.com'
        user.set_password('123456')
        user.save()


class UserManagerConfig(AppConfig):
    name = 'user_manager'

    def ready(self):
        super(UserManagerConfig, self).ready()

        post_migrate.connect(init_user, sender=self)
