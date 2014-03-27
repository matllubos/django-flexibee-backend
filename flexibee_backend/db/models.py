from django.db.models.fields.related import ForeignKey
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.text import slugify

from flexibee_backend import config
from flexibee_backend.is_core.filters import FlexibeeCompanyFieldFilter


class CompanyForeignKey(ForeignKey):
    pass


class StoreViaForeignKey(ForeignKey):
    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name


class Company(models.Model):

    flexibee_db_name = models.CharField(verbose_name=_('DB name'), null=False, blank=False, max_length=100,
                                        unique=True)

    def save(self, *args, **kwargs):
        if not self.flexibee_db_name and self.FlexibeeMeta.db_name_slug_from_field is not None:
            flexibee_db_name_slug = slugify(getattr(self, self.FlexibeeMeta.db_name_slug_from_field))[:90]

            postfix = 0
            while self.__class__._default_manager.filter(flexibee_db_name='%s%s' %
                                                         (flexibee_db_name_slug, postfix or '')):
                postfix += 1

            self.flexibee_db_name = '%s%s' % (flexibee_db_name_slug, postfix or '')
        return super(Company, self).save(*args, **kwargs)

    class Meta:
        abstract = True

    class FlexibeeMeta:
        mapping = {}
        db_name_slug_from_field = None


class FlexibeeModel(models.Model):

    flexibee_company = CompanyForeignKey(config.FLEXIBEE_COMPANY_MODEL, null=True, blank=True, editable=False,
                                         on_delete=models.DO_NOTHING)
    flexibee_company.filter = FlexibeeCompanyFieldFilter

    class Meta:
        abstract = True
