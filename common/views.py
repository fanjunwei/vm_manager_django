# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mimetypes
import os
import posixpath
import stat
from collections import OrderedDict
from urllib import unquote

from django.contrib.staticfiles.finders import get_finders
from django.http import (
    FileResponse, Http404, HttpResponseNotModified,
)
from django.utils.http import http_date
from django.utils.translation import ugettext as _
from django.views.static import was_modified_since

found_files = None


def get_file_list():
    global found_files
    if found_files == None:
        found_files = OrderedDict()
        for finder in get_finders():
            for path, storage in finder.list(None):
                if getattr(storage, 'prefix', None):
                    prefixed_path = os.path.join(storage.prefix, path)
                else:
                    prefixed_path = path

                if prefixed_path not in found_files:
                    source_path = storage.path(path)
                    found_files[prefixed_path] = source_path
    return found_files


def ms_static_serve(request, path):
    path = posixpath.normpath(unquote(path)).lstrip('/')
    fullpath = get_file_list().get(path)

    if not fullpath or not os.path.exists(fullpath):
        raise Http404(_('"%(path)s" does not exist') % {'path': fullpath})
    # Respect the If-Modified-Since header.
    statobj = os.stat(fullpath)
    if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'),
                              statobj.st_mtime, statobj.st_size):
        return HttpResponseNotModified()
    content_type, encoding = mimetypes.guess_type(fullpath)
    content_type = content_type or 'application/octet-stream'
    response = FileResponse(open(fullpath, 'rb'), content_type=content_type)
    response["Last-Modified"] = http_date(statobj.st_mtime)
    if stat.S_ISREG(statobj.st_mode):
        response["Content-Length"] = statobj.st_size
    if encoding:
        response["Content-Encoding"] = encoding
    return response
