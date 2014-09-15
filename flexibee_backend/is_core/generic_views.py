from django.core.urlresolvers import reverse
from django.utils.encoding import force_text

from is_core.generic_views.mixins import TabsViewMixin
from is_core.generic_views.inlines.inline_form_views import StackedInlineFormView, TabularInlineFormView
from is_core.generic_views.exceptions import SaveObjectException

from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseException
from flexibee_backend.db.utils import set_db_name

from .filters import *
from flexibee_backend.is_core.forms import FlexibeeAttachmentForm
from django.forms.formsets import formset_factory


class FlexibeeTabsViewMixin(TabsViewMixin):

    def get_tab_menu_items(self):
        from is_core.menu import LinkMenuItem

        companies = self.core.get_companies(self.request)
        if len(companies) < 2:
            return []

        info = self.site_name, self.core.get_menu_group_pattern_name()
        menu_items = []
        for company in companies:
            url = reverse('%s:list-%s' % info, kwargs={'company': company.pk})
            menu_items.append(LinkMenuItem(force_text(company), url,
                                           self.request.kwargs.get('company') == str(company.pk)))
        return menu_items


class FlexibeeViewMixin(object):

    def dispatch(self, request, *args, **kwargs):
        self.set_db_name(request)
        return super(FlexibeeViewMixin, self).dispatch(request, *args, **kwargs)

    def set_db_name(self, request):
        company = self.get_company(request)
        if company:
            set_db_name(company.flexibee_db_name)

    def get_company(self, request):
        raise NotImplemented


class FlexibeeInlineFormView(object):

    def save_obj(self, obj, change):
        self.pre_save_obj(obj, change)
        try:
            obj.save()
        except FlexibeeDatabaseException as ex:
            raise SaveObjectException(ex.errors)
        self.post_save_obj(obj, change)


class FlexibeeTabularInlineFormView(FlexibeeInlineFormView, TabularInlineFormView):
    pass


class FlexibeeStackedInlineFormView(FlexibeeInlineFormView, StackedInlineFormView):
    pass



class FlexibeeItemInlineFormView(object):
    """
    InlineFormView for special flexibee objects that is firmly connected to another object (can not be implemented as
    standard django model)
    """

    def get_formset(self, instance, data, files):
        print formset_factory(self.form_class, extra=2)

        formset = formset_factory(self.form_class, extra=2)()

        formset.can_add = self.get_can_add()
        formset.can_delete = self.get_can_delete()

        formset.all_forms = formset.forms + [formset.empty_form]
        print formset.all_forms
        for form in formset:
            # TODO: solve exception
            # form.class_names = self.form_class_names(form)
            # self.form_fields(form)
            print form
        return formset

    def get_name(self):
        # TODO: solve
        return 'attachement'

class FlexibeeAttachmentFormView(FlexibeeItemInlineFormView):
    form_class = FlexibeeAttachmentForm


