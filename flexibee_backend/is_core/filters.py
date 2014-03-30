from is_core.filters.default_filters import DefaultFieldFilter

from flexibee_backend.db.utils import set_db_name


class FlexibeeCompanyFieldFilter(DefaultFieldFilter):

    def get_widget(self):
        widget = super(FlexibeeCompanyFieldFilter, self).get_widget()
        widget.extra_fields = False
        widget.choices.field.empty_label = None
        return widget

    def get_company(self):
        Company = self.field.rel.to
        if self.value:
            return Company.objects.get(pk=self.value)
        else:
            return Company.objects.all().first()

    def filter_queryset(self, queryset):
        set_db_name(self.get_company())
        return queryset

    def render(self, request):
        return self.get_widget().render('filter__%s' % self.get_filter_name(), self.get_company().pk,
                                        attrs=self.get_attrs_for_widget())
