from django.db.models.loading import get_model
from django.utils.datastructures import SortedDict
from django.db.transaction import get_connection
from django.core.urlresolvers import reverse
from django.shortcuts import get_object_or_404
from django.db.utils import DatabaseError
from django.http.response import Http404

from is_core.main import UIRestModelISCore, RestModelISCore
from is_core.generic_views.inlines.inline_form_views import TabularInlineFormView
from is_core.generic_views.table_views import TableView
from is_core.rest.resource import RestModelResource
from is_core.patterns import RestPattern, DoubleRestPattern
from is_core.generic_views.form_views import AddModelFormView, EditModelFormView
from is_core.exceptions import SaveObjectException
from is_core.actions import WebAction
from is_core.utils import get_new_class_name
from is_core.rest.factory import modelrest_factory

from flexibee_backend.is_core.patterns import (FlexibeeRestPattern, FlexibeeUIPattern, FlexibeePattern,
                                               AttachmentsFlexibeeUIPattern)
from flexibee_backend import config
from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseException
from flexibee_backend.is_core.views import AttachmentFileView
from flexibee_backend.is_core.rest.resource import AttachmentItemResource, RelationItemResource
from flexibee_backend.models import Attachment

from rest.serializer import *
from rest.data_processor import *


class FlexibeeIsCore(UIRestModelISCore):
    abstract = True
    default_ui_pattern_class = FlexibeePattern
    rest_resource_pattern_class = FlexibeeRestPattern

    def get_view_classes(self):
        view_classes = super(FlexibeeIsCore, self).get_view_classes()
        view_classes['attachment'] = (r'^/(?P<pk>[-\w]+)/attachment/(?P<attachment_pk>[-\d]+)__(?P<attachment_name>.+)$',
                                      AttachmentFileView, AttachmentsFlexibeeUIPattern)
        return view_classes

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

    def get_api_url(self, request):
        return reverse(self.get_api_url_name(), args=(self.get_company(request).pk,))

    def get_add_url(self, request):
        if 'add' in self.ui_patterns:
            return self.ui_patterns.get('add').get_url_string(request,
                                                              kwargs={'company_pk':self.get_company(request).pk})

    def menu_url(self, request):
        return reverse(('%(site_name)s:' + self.menu_url_name) % {'site_name': self.site_name},
                       kwargs={'company_pk': self.get_companies(request).first().pk})

    def get_menu_groups(self):
        return self.menu_parent_groups + [self.menu_group]


class ItemIsCore(RestModelISCore):
    abstract = True

    rest_resource_pattern_class = FlexibeeRestPattern

    def init_request(self, request):
        get_connection(config.FLEXIBEE_BACKEND_NAME).set_db_name('testovaci_firma_ffp')

    def get_company(self, request):
        return get_object_or_404(self.get_companies(request), pk=request.kwargs.get('company_pk'))

    def get_queryset(self, request, parent_group):
        from is_core.site import get_core
        # TODO This is not very secure

        parent_core = get_core(parent_group)
        if not parent_core:
            raise Http404

        return parent_core.get_queryset(request)

    def get_url_prefix(self):
        return (
            'company/(?P<company_pk>[-\w]+)/(?P<parent_group>[-\w]+)/(?P<parent_pk>[-\w]+)/%s' %
            '/'.join(self.get_menu_groups())
        )

    def get_resource_patterns(self):
        return DoubleRestPattern(self.rest_resource_class, self.rest_resource_pattern_class, self).patterns


class AttachmentsIsCore(ItemIsCore):
    rest_resource_class = AttachmentItemResource
    menu_group = 'attachment'


class RelationIsCore(ItemIsCore):
    rest_resource_class = RelationItemResource
    menu_group = 'relation'

