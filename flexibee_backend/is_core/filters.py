from django.db import models

from is_core.filters.default_filters import DefaultFieldFilter

from flexibee_backend.db.utils import set_db_name

from dateutil.parser import parse
from flexibee_backend.db.models import FlexibeeModel


class DateFilter(DefaultFieldFilter):

    comparators = ['gt', 'lt', 'gte', 'lte']

    def get_filter_term(self):
        if '__' in self.filter_key:
            return super(DateTimeFilter, self).get_filter_term()

        value = parse(self.value, dayfirst=True)

        return {self.filter_key: value}


class DateTimeFilter(DateFilter):
    pass


for flexibee_model in models.get_models(include_auto_created=True):
    if issubclass(flexibee_model, FlexibeeModel):
        for field in flexibee_model._meta.fields:
            if isinstance(field, models.DateField):
                field.filter = DateFilter
            elif isinstance(field, models.DateTimeField):
                field.filter = DateTimeFilter
