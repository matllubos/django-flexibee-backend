from django.core.urlresolvers import reverse

from is_core.patterns import RestPattern, UIPattern
from django.utils.datastructures import SortedDict
from is_core.utils import get_new_class_name


class FlexibeePattern(object):

    send_in_rest = False

    def get_kwargs(self, request):
        kwargs = {}
        if '(?P<company_pk>[-\w]+)' in self.url_prefix or '(?P<company_pk>[-\w]+)' in self.url_pattern:
            kwargs['company_pk'] = request.kwargs.get('company_pk')
        return kwargs

    def get_url_string(self, request, obj=None, kwargs=None):
        kwargs = kwargs or {}
        kwargs.update(self.get_kwargs(request))
        if obj:
            kwargs.update(self._get_try_kwarg(obj))
        return reverse(self.pattern, kwargs=kwargs)


class FlexibeeRestPattern(FlexibeePattern, RestPattern):
    pass


class FlexibeeUIPattern(FlexibeePattern, UIPattern):
    pass


class AttachmentsFlexibeeUIPattern(FlexibeeUIPattern):
    send_in_rest = False

