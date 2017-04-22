import json
from collections import OrderedDict

import django
import re

from django.conf import settings
from django.core import serializers
from django.core.checks import run_checks
from django.utils.encoding import force_text

from django.db import connection
from django.views.debug import get_safe_settings

from django.utils.functional import Promise
from django.core.serializers.json import DjangoJSONEncoder
from django.urls import resolve


_HTML_TYPES = ('text/html', 'application/xhtml+xml')


class LazyEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Promise):
            return force_text(obj)
        return super(LazyEncoder, self).default(obj)


def debug_payload(request, response):

    current_session = {}

    if 'django.contrib.sessions' in settings.INSTALLED_APPS:
        if request.session.items():
            for k,v in request.session.items():
                current_session[k] = v

    if request.user.is_anonymous:
        user_data = "[\"Anonymous User\"]"
    else:
        user_data = serializers.serialize("json", [request.user])

    resolved_url = resolve(request.path)

    view_data = {
        'view_name': resolved_url._func_path,
        'view_args': resolved_url.args,
        'view_kwargs': resolved_url.kwargs,
    }

    checks = {}
    raw_checks = run_checks(include_deployment_checks=True)

    for check in raw_checks:
        checks[check.id] = check.msg

    payload = {
        'version': django.VERSION,
        'current_user': json.loads(user_data)[0],
        'db_queries': connection.queries,
        'session': current_session,
        'view_data': view_data,
        'url_name': resolved_url.url_name,
        'url_namespaces': resolved_url.namespaces,
        'checks': checks,
        'settings': OrderedDict(sorted(get_safe_settings().items(), key=lambda s: s[0]))
    }

    payload_script = "<script>var dj_chrome = {};</script>".format(json.dumps(payload,
                                                                              cls=LazyEncoder))

    return payload_script


class DebugMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response
        self._view_data = {}
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # For debug only.
        if not settings.DEBUG:
            return response

        # Check for responses where the data can't be inserted.
        content_encoding = response.get('Content-Encoding', '')
        content_type = response.get('Content-Type', '').split(';')[0]
        if any((getattr(response, 'streaming', False),
                'gzip' in content_encoding,
                content_type not in _HTML_TYPES)):
            return response

        content = force_text(response.content, encoding=settings.DEFAULT_CHARSET)

        pattern = re.escape('</body>')
        bits = re.split(pattern, content, flags=re.IGNORECASE)

        if len(bits) > 1:
            bits[-2] += debug_payload(request, response)
            response.content = "</body>".join(bits)
            if response.get('Content-Length', None):
                response['Content-Length'] = len(response.content)

        return response
