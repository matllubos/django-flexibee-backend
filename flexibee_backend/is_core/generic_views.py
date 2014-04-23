from django.core.urlresolvers import reverse
from django.utils.encoding import force_text

from is_core.generic_views.form_views import AddModelFormView, EditModelFormView
from is_core.generic_views.mixins import TabsViewMixin
from is_core.generic_views.inline_form_views import StackedInlineFormView, TabularInlineFormView
from is_core.generic_views.table_views import TableView
from is_core.generic_views.exceptions import SaveObjectException

from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseException
from flexibee_backend.db.utils import set_db_name

from .filters import *


class ListParentMixin(object):

    add_current_to_breadcrumbs = True

    def list_bread_crumbs_menu_item(self):
        from is_core.templatetags.menu import MenuItem

        return MenuItem(self.model._ui_meta.list_verbose_name %
                        {'verbose_name': self.model._meta.verbose_name,
                         'verbose_name_plural': self.model._meta.verbose_name_plural},
                        reverse('%s:list-%s' % (self.site_name, self.core.get_menu_group_pattern_name()),
                                kwargs={'company_pk': self.core.get_company(self.request).pk}),
                                       not self.add_current_to_breadcrumbs)


class FlexibeeDefaultCoreModelFormView(object):

    def get_cancel_url(self):
        if 'list' in self.core.ui_patterns \
                and self.core.ui_patterns.get('list').view.has_get_permission(self.request) \
                and not self.has_snippet():
            info = self.site_name, self.core.get_menu_group_pattern_name()
            return reverse('%s:list-%s' % info,
                           kwargs={'company_pk': self.core.get_company(self.request).pk})
        return None

    def get_success_url(self, obj):
        info = self.site_name, self.core.get_menu_group_pattern_name()
        if 'list' in self.core.ui_patterns \
                and self.core.ui_patterns.get('list').view.has_get_permission(self.request) \
                and 'save' in self.request.POST:
            return reverse('%s:list-%s' % info,
                           kwargs={'company_pk': self.core.get_company(self.request).pk})
        elif 'edit' in self.core.ui_patterns \
                and self.core.ui_patterns.get('edit').view.has_get_permission(self.request) \
                and 'save-and-continue' in self.request.POST:
            return reverse('%s:edit-%s' % info,
                           kwargs={'pk': obj.pk,
                                   'company_pk': self.core.get_company(self.request).pk})
        return ''


class FlexibeeTabsViewMixin(TabsViewMixin):

    def get_tab_menu_items(self):
        from is_core.templatetags.menu import MenuItem

        companies = self.core.get_companies(self.request)
        if len(companies) < 2:
            return []

        info = self.site_name, self.core.get_menu_group_pattern_name()
        menu_items = []
        for company in companies:
            url = reverse('%s:list-%s' % info, kwargs={'company': company.pk})
            menu_items.append(MenuItem(force_text(company), url,
                                       self.request.kwargs.get('company') == str(company.pk)))
        return menu_items


class FlexibeeAddModelFormView(ListParentMixin, FlexibeeDefaultCoreModelFormView,
                               AddModelFormView):
    pass


class FlexibeeEditModelFormView(ListParentMixin, FlexibeeDefaultCoreModelFormView,
                                EditModelFormView):
    pass


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
