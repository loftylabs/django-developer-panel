import json
from collections import OrderedDict
from collections import defaultdict

import django
import inspect
import re

from django.conf import settings
from django.core import serializers
from django.core.checks import run_checks
from django.utils.encoding import force_text

from django.db import connection
from django.views.debug import get_safe_settings

from django.utils.functional import Promise
from django.core.serializers.json import DjangoJSONEncoder

try:
    from django.urls import resolve
except ImportError:
    from django.core.urlresolvers import resolve

from django.views.generic.base import ContextMixin

_HTML_TYPES = ('text/html', 'application/xhtml+xml')


class LazyEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Promise):
            return force_text(obj)
        return super(LazyEncoder, self).default(obj)


def debug_payload(request, response, view_data):

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

    view = {
        'view_name': resolved_url._func_path,
        'view_args': resolved_url.args,
        'view_kwargs': resolved_url.kwargs,
        'view_methods': VIEW_METHOD_DATA,
        'cbv': view_data.get('cbv', False),
        'bases': view_data.get('bases', []),
    }

    checks = {}
    raw_checks = run_checks(include_deployment_checks=True)

    for check in raw_checks:
        checks[check.id] = check.msg

    json_friendly_settings = OrderedDict()
    s = get_safe_settings()
    for key in sorted(s.keys()):
        json_friendly_settings[key] = str(s[key])

    payload = {
        'version': django.VERSION,
        'current_user': json.loads(user_data)[0],
        'db_queries': connection.queries,
        'session': current_session,
        'view_data': view,
        'url_name': resolved_url.url_name,
        'url_namespaces': resolved_url.namespaces,
        'checks': checks,
        'settings': json_friendly_settings
    }

    payload_script = "<script>var dj_chrome = {};</script>".format(json.dumps(payload,
                                                                              cls=LazyEncoder))

    return payload_script


VIEW_METHOD_WHITEIST = [
    'get_context_data',
    'get_template_names',
    'get_queryset',
    'get_object',
    'get_form_class',
    'get_form_kwargs',
    'get_redirect_field_name',
    'get_slug_field',
    'get_context_object_name',
    'get_login_url',
    'http_method_not_allowed',
]

VIEW_METHOD_DATA = {}
PATCHED_METHODS = defaultdict(list)


def record_view_data(f):
    def wrapper(self, *args, **kwargs):
        retval = f(self, *args, **kwargs)

        VIEW_METHOD_DATA[f.__name__] = {
            'args': repr(args),
            'kwargs': repr(kwargs),
            'return': repr(retval)
        }

        return retval
    return wrapper


def decorate_method(klass, method):
    attached_method = getattr(klass, method)
    patched_method = record_view_data(attached_method)
    setattr(klass, method, patched_method)
    return patched_method


class DebugMiddleware:
    """
    Should be new-style and old-style compatible.
    """

    def __init__(self, next_layer=None):
        """We allow next_layer to be None because old-style middlewares
        won't accept any argument.
        """
        self.get_response = next_layer

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Collect data on Class-Based Views
        """

        # Purge data in view method cache
        # Python 3's keys() method returns an iterator, so force evaluation before iterating.
        view_keys = list(VIEW_METHOD_DATA.keys())
        for key in view_keys:
            del VIEW_METHOD_DATA[key]

        self.view_data = {}

        try:
            cbv = view_func.view_class
        except AttributeError:
            cbv = False

        if cbv:

            self.view_data['cbv'] = True
            klass = view_func.view_class
            self.view_data['bases'] = [base.__name__ for base in inspect.getmro(klass)]
            # Inject with drugz

            for member in inspect.getmembers(view_func.view_class):
                # Check that we are interested in capturing data for this method
                # and ensure that a decorated method is not decorated multiple times.
                if member[0] in VIEW_METHOD_WHITEIST and member[0] not in PATCHED_METHODS[klass]:
                    decorate_method(klass, member[0])
                    PATCHED_METHODS[klass].append(member[0])

    def process_template_response(self, request, response):

        if response.context_data is None:
            return response

        view = response.context_data.get('view', None)

        if ContextMixin in self.view_data.get('bases', []):
            self.view_data['context'] = view.get_context_data()

        return response

    def process_request(self, request):
        """Let's handle old-style request processing here, as usual."""
        # Do something with request
        # Probably return None
        # Or return an HttpResponse in some cases

    def process_response(self, request, response):
        """Let's handle old-style response processing here, as usual."""

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
            bits[-2] += debug_payload(request, response, self.view_data)
            response.content = "</body>".join(bits)
            if response.get('Content-Length', None):
                response['Content-Length'] = len(response.content)

        return response

    def __call__(self, request):
        """Handle new-style middleware here."""
        response = self.process_request(request)
        if response is None:
            # If process_request returned None, we must call the next middleware or
            # the view. Note that here, we are sure that self.get_response is not
            # None because this method is executed only in new-style middlewares.
            response = self.get_response(request)
        response = self.process_response(request, response)
        return response
