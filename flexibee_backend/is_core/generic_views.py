from django.core.urlresolvers import reverse
from django.utils.encoding import force_text

from is_core.generic_views.form_views import AddModelFormView, EditModelFormView
from is_core.generic_views.mixins import TabsViewMixin

from is_core.generic_views.table_views import TableView

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
                                kwargs={'flexibee_db_name': self.core.get_company(self.request).flexibee_db_name}),
                                       not self.add_current_to_breadcrumbs)


class FlexibeeDefaultCoreModelFormView(object):

    def get_cancel_url(self):
        if 'list' in self.core.ui_patterns \
                and self.core.ui_patterns.get('list').view.has_get_permission(self.request, self.core) \
                and not self.has_snippet():
            info = self.site_name, self.core.get_menu_group_pattern_name()
            return reverse('%s:list-%s' % info,
                           kwargs={'flexibee_db_name': self.core.get_company(self.request).flexibee_db_name})
        return None

    def get_success_url(self, obj):
        info = self.site_name, self.core.get_menu_group_pattern_name()
        if 'list' in self.core.ui_patterns \
                and self.core.ui_patterns.get('list').view.has_get_permission(self.request, self.core) \
                and 'save' in self.request.POST:
            return reverse('%s:list-%s' % info,
                           kwargs={'flexibee_db_name': self.core.get_company(self.request).flexibee_db_name})
        elif 'edit' in self.core.ui_patterns \
                and self.core.ui_patterns.get('edit').view.has_get_permission(self.request, self.core) \
                and 'save-and-continue' in self.request.POST:
            return reverse('%s:edit-%s' % info,
                           kwargs={'pk': obj.pk,
                                   'flexibee_db_name': self.core.get_company(self.request).flexibee_db_name})
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
            url = reverse('%s:list-%s' % info, kwargs={'flexibee_db_name': company.flexibee_db_name})
            menu_items.append(MenuItem(force_text(company), url,
                                       self.request.kwargs.get('flexibee_db_name') == company.flexibee_db_name))
        return menu_items


class FlexibeeAddModelFormView(FlexibeeTabsViewMixin, ListParentMixin,
                               FlexibeeDefaultCoreModelFormView, AddModelFormView):
    pass


class FlexibeeEditModelFormView(FlexibeeTabsViewMixin, ListParentMixin,
                                FlexibeeDefaultCoreModelFormView, EditModelFormView):
    pass

class FlexibeeTableView(FlexibeeTabsViewMixin, TableView):
    pass


class FlexibeeViewMixin(object):

    def dispatch(self, request, *args, **kwargs):
        company = self.get_company(request)
        if company:
            set_db_name(company.flexibee_db_name)
        return super(FlexibeeViewMixin, self).dispatch(request, *args, **kwargs)

    def get_company(self, request):
        raise NotImplemented
