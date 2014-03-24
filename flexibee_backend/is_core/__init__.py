from django.db.models.loading import get_model

from is_core.main import UIRestModelISCore
from is_core.generic_views.inline_form_views import TabularInlineFormView

from flexibee_backend import config


class FlexibeeIsCore(UIRestModelISCore):

    def get_queryset(self, request):
        company = get_model(*config.FLEXIBEE_COMPANY_MODEL.rsplit('.', 1)).objects.all().first()


        return self.model._default_manager.get_queryset().filter(flexibee_company=company)
