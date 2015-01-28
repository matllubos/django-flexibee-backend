from django.utils.translation import ugettext_lazy as _

from is_core.generic_views.inlines.inline_form_views import StackedInlineFormView, TabularInlineFormView
from is_core.exceptions import PersistenceException
from is_core.forms.formsets import smartformset_factory
from is_core.forms.forms import smartform_factory

from flexibee_backend.db.backends.rest.exceptions import FlexibeeResponseError
from flexibee_backend.is_core.forms import FlexibeeAttachmentForm
from flexibee_backend.is_core.forms.formsets import ItemBaseFormSet


class FlexibeeInlineFormView(object):

    def save_obj(self, obj, change):
        self.pre_save_obj(obj, change)
        try:
            obj.save()
        except FlexibeeResponseError as ex:
            raise PersistenceException(ex.errors)
        self.post_save_obj(obj, change)


class FlexibeeTabularInlineFormView(FlexibeeInlineFormView, TabularInlineFormView):
    pass


class FlexibeeStackedInlineFormView(FlexibeeInlineFormView, StackedInlineFormView):
    pass


class FlexibeeItemInlineFormViewMixin(object):
    """
    InlineFormView for special flexibee objects that is firmly connected to another object (can not be implemented as
    standard django model)
    """

    def get_formset(self, instance, data, files):
        """
        Rewrited because there is different formset factory
        """
        extra = self.get_extra()
        readonly_fields = self.get_readonly_fields()
        exclude = self.get_exclude()

        form_class = smartform_factory(self.request, self.form_class, readonly_fields=readonly_fields, exclude=exclude,
                                       formreadonlyfield_callback=self.formfield_for_readonlyfield,
                                       readonly=self.readonly)
        Formset = smartformset_factory(form_class, formset=ItemBaseFormSet, extra=extra, min_num=self.min_num,
                                       max_num=self.max_num)
        if data:
            formset = Formset(instance, self.get_queryset(), data=data, files=files,
                                                   prefix=self.get_prefix())
        else:
            formset = Formset(instance, self.get_queryset(), prefix=self.get_prefix())

        formset.can_add = self.get_can_add()
        formset.can_delete = self.get_can_delete()

        for form in formset:
            form.class_names = self.form_class_names(form)
            self.form_fields(form)
        return formset

    def form_field(self, form, field_name, form_field):
        """
        Rewrited because there is no model
        """
        return form_field

    def form_class_names(self, form):
        """
        Rewrited because there is no model
        """
        if not form.instance:
            return ['empty']
        return []

    def get_queryset(self):
        """
        Should return list of items related to instance
        """
        raise NotImplementedError

    def form_valid(self, request):
        """
        Rewrited because is_changed is get with different way
        """
        instances = self.formset.save(commit=False)
        for obj in instances:
            self.save_obj(obj, obj.is_stored)
        for obj in self.formset.deleted_objects:
            self.delete_obj(obj)

    def get_name(self):
        """
        Should contain human readable name for adding button
        """
        raise NotImplementedError


class FlexibeeAttachmentFormViewMixin(FlexibeeItemInlineFormViewMixin):
    form_class = FlexibeeAttachmentForm

    def get_name(self):
        return 'attachment'

    def get_queryset(self):
        return self.parent_instance.attachments.all()
