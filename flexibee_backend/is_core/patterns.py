from is_core.patterns import RestPattern, UIPattern


class FlexibeePattern(object):

    def _get_try_kwarg(self, obj):
        kwargs = {'company_pk': obj.flexibee_company.pk}

        if'(?P<pk>[-\w]+)' in self.url_pattern or '(?P<pk>\d+)' in self.url_pattern:
            kwargs['pk'] = obj.pk

        return kwargs


class FlexibeeRestPattern(FlexibeePattern, RestPattern):
    pass


class FlexibeeUIPattern(FlexibeePattern, UIPattern):
    pass
