from django.core.management.base import NoArgsCommand

from django.db import models
from flexibee_backend.models import FlexibeeModel
from flexibee_backend import config
from flexibee_backend.db.utils import set_db_name


class Command(NoArgsCommand):

    def handle_noargs(self, **options):
        for company in models.get_model(*config.FLEXIBEE_COMPANY_MODEL.split('.', 1))._default_manager.all():
            set_db_name(company.flexibee_db_name)
            for model in models.get_models():
                if issubclass(model, FlexibeeModel) and model._internal_model:
                    model._internal_model._default_manager.filter(flexibee_company=company).exclude(
                            flexibee_obj_id__in=model._default_manager.values_list('id', flat=True)
                    )
