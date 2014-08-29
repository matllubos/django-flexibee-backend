from .fields import *

from django.db import models
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _

from flexibee_backend.db.backends.rest.utils import db_name_validator
from flexibee_backend.db.backends.rest.admin_connection import admin_connector
from flexibee_backend.db.backends.rest.exceptions import SyncException


class Company(models.Model):

    flexibee_db_name = models.CharField(verbose_name=_('DB name'), null=False, blank=True, max_length=100,
                                        unique=True, validators=[db_name_validator])

    class Meta:
        abstract = True

    class FlexibeeMeta:
        create_mapping = {}
        update_mapping = {}
        db_name_slug_from_field = None
        readonly_fields = []


class FlexibeeModel(models.Model):

    flexibee_company = CompanyForeignKey(config.FLEXIBEE_COMPANY_MODEL, null=True, blank=True, editable=False,
                                         on_delete=models.DO_NOTHING)


    def attachements(self):
        return

    class Meta:
        abstract = True

    class FlexibeeMeta:
        readonly_fields = []
