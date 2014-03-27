from is_core.filters.default_filters import DefaultFieldFilter


class FlexibeeCompanyFieldFilter(DefaultFieldFilter):

    def get_widget(self):
        print 'dddd'
        widget = super(FlexibeeCompanyFieldFilter, self).get_widget()
        widget.extra_fields = False
        return widget

    def filter_queryset(self, queryset):
        print 'ted'
        return queryset
