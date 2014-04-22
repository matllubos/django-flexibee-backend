from is_core.patterns import RestPattern, UIPattern


class FlexibeePatter(object):

    def _get_try_kwarg(self, obj):
        kwargs = {'company': obj.flexibee_company.pk}

        if'(?P<pk>[-\w]+)' in self.url_pattern or '(?P<pk>\d+)' in self.url_pattern:
            kwargs['pk'] = obj.pk

        return kwargs


class FlexibeeRestPattern(FlexibeePatter, RestPattern):
    pass


class FlexibeeUIPattern(FlexibeePatter, UIPattern):
    pass
