from django.core.urlresolvers import reverse

from is_core.patterns import RestPattern, UIPattern


class FlexibeePattern(object):

    def _get_try_kwargs(self, request, obj):
        kwargs = super(FlexibeePattern, self)._get_try_kwargs(request, obj)
        if '(?P<company_pk>[-\w]+)' in self.url_prefix or '(?P<company_pk>[-\w]+)' in self.url_pattern:
            kwargs['company_pk'] = request.kwargs.get('company_pk')
        return kwargs


class FlexibeeRestPattern(FlexibeePattern, RestPattern):
    pass


class FlexibeeUIPattern(FlexibeePattern, UIPattern):
    pass


class AttachmentsFlexibeeUIPattern(FlexibeeUIPattern):
    send_in_rest = False
