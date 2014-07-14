from django.db.models.loading import get_model
from django.utils.datastructures import SortedDict
from django.db.transaction import get_connection
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.db.utils import DatabaseError

from is_core.main import UIRestModelISCore
from is_core.generic_views.inlines.inline_form_views import TabularInlineFormView
from is_core.generic_views.table_views import TableView
from is_core.rest.resource import RestModelResource
from is_core.patterns import RestPattern
from is_core.generic_views.form_views import AddModelFormView, EditModelFormView
from is_core.generic_views.exceptions import SaveObjectException
from is_core.actions import WebAction

from flexibee_backend.is_core.patterns import FlexibeeRestPattern, FlexibeeUIPattern, FlexibeePattern
from flexibee_backend import config
from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseException


class FlexibeeIsCore(UIRestModelISCore):
    abstract = True
    default_ui_pattern_class = FlexibeePattern

    def save_model(self, request, obj, form, change):
        try:
            obj.save()
        except FlexibeeDatabaseException as ex:
            raise SaveObjectException(ex.errors)

    def get_show_in_menu(self, request):
        return self.get_companies(request).exists()

    def init_request(self, request):
        get_connection(config.FLEXIBEE_BACKEND_NAME).set_db_name(self.get_company(request).flexibee_db_name)

    def get_companies(self, request):
        raise NotImplemented

    def get_company(self, request):
        return get_object_or_404(self.get_companies(request), pk=request.kwargs.get('company_pk'))

    def get_url_prefix(self):
        return 'company/(?P<company_pk>[-\w]+)/%s' % '/'.join(self.get_menu_groups())

    def get_resource_patterns(self):
        resource_patterns = SortedDict()
        resource_patterns['api-resource'] = FlexibeeRestPattern('api-resource-%s' % self.get_menu_group_pattern_name(),
                                                                self.site_name, r'^/api/(?P<pk>[-\w]+)/?$',
                                                                self.rest_resource, self, ('GET', 'PUT', 'DELETE'))
        resource_patterns['api'] = FlexibeeRestPattern('api-%s' % self.get_menu_group_pattern_name(), self.site_name,
                                                       r'^/api/?$', self.rest_resource, self, ('GET', 'POST'))
        return resource_patterns

    def get_api_url(self, request):
        return reverse(self.get_api_url_name(), args=(self.get_company(request).pk,))

    def get_add_url(self, request):
        return self.ui_patterns.get('add').get_url_string(request, kwargs={'company_pk':self.get_company(request).pk})

    def menu_url(self, request):
        return reverse(('%(site_name)s:' + self.menu_url_name) % {'site_name': self.site_name},
                       kwargs={'company_pk': self.get_companies(request).first().pk})

    def get_menu_groups(self):
        return self.menu_parent_groups + [self.menu_group]
