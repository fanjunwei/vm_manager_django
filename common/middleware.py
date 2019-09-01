# coding=utf-8
from threading import local

from django import http
from django.conf import settings
from django.utils.cache import get_conditional_response, set_response_etag, cc_delim_re
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import parse_http_date_safe

current_request = local()


def getCurrentRequest():
    """
    获取当前request
    :return:
    """
    if hasattr(current_request, 'request'):
        return current_request.request
    else:
        return None


def setCurrentRequest(request):
    """
    设置当前request
    :return:
    """
    if request:
        current_request.request = request


class GlobRequestMiddleware(MiddlewareMixin):
    """
    存储当前request中间件
    """

    def process_request(self, request):
        current_request.request = request


class CorsDomainMiddleware(MiddlewareMixin):
    def process_request(self, request):
        method = request.method.upper()
        if method == "OPTIONS":
            response = http.HttpResponse("OPTIONS")
            origin = request.META.get("HTTP_ORIGIN")
            if origin:
                response['Access-Control-Allow-Credentials'] = "true"
                response['Access-Control-Allow-Origin'] = origin
            else:
                response['Access-Control-Allow-Origin'] = "*"
            response['Access-Control-Allow-Headers'] = "Content-Type,X-Auth-Token,x-access-module"
            response['Access-Control-Expose-Headers'] = "Content-Type,Set-Auth-Token,Set-Client"
            response['Access-Control-Allow-Methods'] = "GET,POST,PUT,DELETE"
            return response

    def process_response(self, request, response):
        origin = request.META.get("HTTP_ORIGIN")
        if origin:
            response['Access-Control-Allow-Credentials'] = "true"
            response['Access-Control-Allow-Origin'] = origin
        else:
            response['Access-Control-Allow-Origin'] = "*"
        response['Access-Control-Allow-Headers'] = "Content-Type,X-Auth-Token,x-access-module"
        response['Access-Control-Expose-Headers'] = "Content-Type,Set-Auth-Token,Set-Client"
        response['Access-Control-Allow-Methods'] = "GET,POST,PUT,DELETE"
        return response


class ETagMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # It's too late to prevent an unsafe request with a 412 response, and
        # for a HEAD request, the response body is always empty so computing
        # an accurate ETag isn't possible.

        if self.needs_etag(response) and not response.has_header('ETag'):
            set_response_etag(response)

        etag = response.get('ETag')
        last_modified = response.get('Last-Modified')
        if last_modified:
            last_modified = parse_http_date_safe(last_modified)

        if etag or last_modified:
            return get_conditional_response(
                request,
                etag=etag,
                last_modified=last_modified,
                response=response,
            )

        return response

    def needs_etag(self, response):
        """
        Return True if an ETag header should be added to response.
        """
        cache_control_headers = cc_delim_re.split(response.get('Cache-Control', ''))
        return all(header.lower() != 'no-store' for header in cache_control_headers)


class SessionTransferMiddleware(MiddlewareMixin):
    """
    session_id传递
    """

    def parase(self, query_string):
        result = {}
        for i in query_string.split("&"):
            args = i.split('=', 1)
            if len(args) == 2:
                result[args[0]] = args[1]

        return result

    def process_request(self, request):
        query_string = request.META['QUERY_STRING']
        query_params = self.parase(query_string)

        session_key = query_params.get("token")
        request.header_session_key = session_key
        if session_key:
            request.COOKIES[settings.SESSION_COOKIE_NAME] = session_key

    def process_response(self, request, response):
        if hasattr(request, 'header_session_key') and request.header_session_key:
            response.set_cookie(settings.SESSION_COOKIE_NAME, request.header_session_key)
        return response
