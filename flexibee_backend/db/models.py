from django.db.models.fields.related import ForeignKey
from django.db import models
from django.utils.translation import ugettext_lazy as _

from flexibee_backend import config


class CompanyForeignKey(ForeignKey):
    pass


class StoreViaForeignKey(ForeignKey):
    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name


class Company(models.Model):

    flexibee_db_name = models.CharField(verbose_name=_('DB name'), null=False, blank=False, max_length=100,
                                        unique=True)

    class Meta:
        abstract = True

    class FlexibeeMeta:
        mapping = {}


class FlexibeeModel(models.Model):

    flexibee_company = CompanyForeignKey(config.FLEXIBEE_COMPANY_MODEL, null=True, blank=True, editable=False)

    class Meta:
        abstract = True
