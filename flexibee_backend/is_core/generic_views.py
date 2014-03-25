from django.forms.models import ModelChoiceField

from is_core.generic_views.inline_form_views import TabularInlineFormView, StackedInlineFormView
from is_core.generic_views.form_views import AddModelFormView, EditModelFormView

from flexibee_backend.db.models import ForeignKey, FlexibeeModel


class FlexibeeInlineFormViewMixin(object):

    def get_queryset(self):
        return self.model.objects.filter(flexibee_company=self.core.get_company())

    def form_fields(self, form):
        form.instance.flexibee_company = self.core.get_company()
        super(FlexibeeInlineFormViewMixin, self).form_fields(form)

    def form_field(self, form, field_name, form_field):
        if isinstance(form_field, ModelChoiceField) and issubclass(form_field.queryset.model, FlexibeeModel):
            form_field.queryset = form_field.queryset.filter(flexibee_company=self.core.get_company())
        return form_field


class FlexibeeTabularInlineFormView(FlexibeeInlineFormViewMixin, TabularInlineFormView):
    pass


class FlexibeeStackedInlineFormView(FlexibeeInlineFormViewMixin, StackedInlineFormView):
    pass


class FlexibeeDefaultCoreModelFormViewMixin(object):

    def formfield_for_dbfield(self, db_field, **kwargs):
        field = db_field.formfield(**kwargs)
        if isinstance(db_field, ForeignKey):
            field.queryset = field.queryset.filter(flexibee_company=self.core.get_company())

        return field


class FlexibeeAddModelFormView(FlexibeeDefaultCoreModelFormViewMixin, AddModelFormView):

    def get_obj(self, cached=True):
        return self.model(flexibee_company=self.core.get_company())


class FlexibeeEditModelFormView(FlexibeeDefaultCoreModelFormViewMixin, EditModelFormView):
    pass
