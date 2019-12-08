# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth import login, authenticate
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class LoginView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        username = self.request.data.get("userName")
        password = self.request.data.get("password")

        user = authenticate(username=username, password=password)
        if not user:
            raise exceptions.ValidationError("用户名或密码错误")

        if not user.is_active:
            raise exceptions.ValidationError("用户已禁用")

        login(self.request._request, user)
        return Response(data={
            "name": username,
            "user_id": user.id,
            "access": ['super_admin', 'admin'],
            "token": self.request._request.session.session_key,
            "avatar": 'https://file.iviewui.com/dist/'
                      'a0e88e83800f138b94d2414621bd9704.png'

        })


class GetInfoView(APIView):

    def get(self, request, *args, **kwargs):
        user = self.request.user

        return Response(data={
            "name": user.username,
            "user_id": user.id,
            "access": ['super_admin', 'admin'],
            "token": self.request._request.session.session_key,
            "avatar": 'https://file.iviewui.com/dist/'
                      'a0e88e83800f138b94d2414621bd9704.png'
        })
