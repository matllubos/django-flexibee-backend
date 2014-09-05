from .fields import *

from django.db import models
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _

from flexibee_backend.db.backends.rest.utils import db_name_validator
from flexibee_backend.db.backends.rest.admin_connection import admin_connector
from flexibee_backend.db.backends.rest.exceptions import SyncException
from flexibee_backend import config
from flexibee_backend.db.backends.rest.connection import ModelConnector
from django.db.models.base import ModelBase


class OptionsLazy(object):

    def __init__(self, name, klass):
        self.name = name
        self.klass = klass

    def __get__(self, instance=None, owner=None):
        print self.klass
        option = self.klass(owner)
        print self.klass(owner)
        setattr(owner, self.name, option)
        return option


class Options(object):

    def __init__(self, model):
        self.model = model


class FlexibeeOptions(Options):

    def __getattr__(self, name):
        models = [b for b in self.model.__mro__ if issubclass(b, FlexibeeModel)]
        for model in models:
            value = getattr(model.FlexibeeMeta, name, None)
            print model
            print value
            if value is not None:
                return value


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
    attachments = AttachmentsField(_('Attachments'), null=True, blank=True, editable=False)

    _flexibee_meta = OptionsLazy('_flexibee_meta', FlexibeeOptions)

    class Meta:
        abstract = True

    class FlexibeeMeta:
        readonly_fields = []
        db_connector = ModelConnector

