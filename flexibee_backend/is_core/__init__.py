from django.db.models.loading import get_model

from is_core.main import UIRestModelISCore
from is_core.generic_views.inline_form_views import TabularInlineFormView

from flexibee_backend import config
from flexibee_backend.is_core.generic_views import FlexibeeAddModelFormView, FlexibeeEditModelFormView
from is_core.generic_views.table_views import TableView
from django.utils.datastructures import SortedDict


class FlexibeeIsCore(UIRestModelISCore):

    view_classes = SortedDict((
                    ('add', (r'^/add/$', FlexibeeAddModelFormView)),
                    ('edit', (r'^/(?P<pk>[-\w]+)/$', FlexibeeEditModelFormView)),
                    ('list', (r'^/?$', TableView)),
                ))

    def get_company(self):
        return get_model(*config.FLEXIBEE_COMPANY_MODEL.rsplit('.', 1)).objects.all().first()

    def get_queryset(self, request):
        return self.model._default_manager.get_queryset().filter(flexibee_company=self.get_company())
