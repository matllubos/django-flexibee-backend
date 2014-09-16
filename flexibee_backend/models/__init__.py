import decimal

from .fields import *

from django.db import models
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _
from django.db.models.base import ModelBase
from django.utils.functional import SimpleLazyObject
from django.core.exceptions import ValidationError

from flexibee_backend.db.backends.rest.utils import db_name_validator
from flexibee_backend.db.backends.rest.admin_connection import admin_connector
from flexibee_backend.db.backends.rest.exceptions import SyncException, FlexibeeDatabaseException
from flexibee_backend.db.backends.rest.connection import AttachmentConnector, RelationConnector
from flexibee_backend import config
from flexibee_backend.models.utils import get_model_by_db_table, lazy_obj_loader


class FlexibeeItem(object):
    """
    Class which represents model for objects which is firmly connected to other real db model
    """

    connector_class = None
    stored = False

    def __init__(self, instance, connector, data=None, **kwargs):
        self.instance = instance
        self.connector = connector
        if data is not None:
            self.stored = True
            self._decode(data)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def _decode(self, data):
        """
        There should be added code which implements data dencoding from flexibee backend
        """
        raise NotImplementedError

    def _encode(self, data):
        """
        There should be added code which implements data encoding for flexibee backend
        """
        raise NotImplementedError

    def delete(self):
        self._delete()
        self.stored = False

    def save(self):
        self._save()
        self.stored = True

    def _delete(self):
        """
        There should be added code which implements calls connector for deleting object
        """
        raise NotImplementedError

    def _save(self):
        """
        There should be added code which implements calls connector for creating or updating object
        """
        raise NotImplementedError

    def __str__(self):
        return self.__unicode__()


class Attachment(FlexibeeItem):
    """
    Attachements for all flexibee objects
    """

    connector_class = AttachmentConnector

    filename = None
    file = None

    def _decode(self, data):
        self.filename = data.get('nazSoub')
        self.content_type = data.get('contentType')
        self.pk = data.get('id')

    def __unicode__(self):
        return self.filename

    def _delete(self):
        self.connector.delete(self.instance._meta.db_table, self.instance.pk, self.pk)

    def _save(self):
        if not self.file or not self.filename:
            raise ValidationError('File and filename is required.')
        self.connector.write(self.instance._meta.db_table, self.instance.pk, self.filename, self.file,
                             self.content_type)

    @property
    def file_response(self):
        if not self.instance or not self.connector:
            raise AttributeError('The %s attachment must be firstly stored.' % (self.filename))

        r = self.connector.get_response(self.instance._meta.db_table, self.instance.pk, self.pk)
        return HttpResponse(r.content, content_type=r.headers['content-type'])


class Relation(FlexibeeItem):
    """
    Relations among pokladni-pohyb,banka/faktura-vydana,faktura-prijata
    Relation work for both sides:
        pokladni-pohyb,banka => faktura-vydana,faktura-prijata
        faktura-vydana,faktura-prijata => pokladni-pohyb,banka
    """

    REMAIN_IGNORE = 'ignorovat'
    REMAIN_NOT_ACCEPT = 'ne'
    REMAIN_RECORD = 'zauctovat'
    REMAIN_PARTIAL_PAYMENT = 'castecnaUhrada'
    REMAIN_PARTIAL_PAYMENT_OR_RECORD = 'castecnaUhradaNeboZauctovat'
    REMAIN_PARTIAL_PAYMENT_OR_IGNORE = 'castecnaUhradaNeboIgnorovat'

    REMAIN_CHOICES = (
        (REMAIN_NOT_ACCEPT, _('Not accept')),
        (REMAIN_IGNORE, _('Ignore')),
        (REMAIN_RECORD, _('Record')),
        (REMAIN_PARTIAL_PAYMENT, _('Partial payment')),
        (REMAIN_PARTIAL_PAYMENT_OR_RECORD, _('Partial payment or record')),
        (REMAIN_PARTIAL_PAYMENT_OR_IGNORE, _('Partial payment or ignore')),
    )
    connector_class = RelationConnector
    invoice = None
    payment = None
    remain = None

    def __init__(self, instance, connector, data=None, **kwargs):
        super(Relation, self).__init__(instance, connector, data, **kwargs)
        if self.instance._meta.db_table in ['pokladni-pohyb', 'banka']:
            self.payment = self.instance
        elif self.instance._meta.db_table in ['faktura-vydana', 'faktura-prijata']:
            self.invoice = self.instance

    def _get_related_obj(self, data, field_name):
        related_model = get_model_by_db_table(data['%s@ref' % field_name].split('/')[-2])
        return lazy_obj_loader(related_model, {'pk': data['%s@ref' % field_name].split('/')[-1][:-5]},
                               self.instance.flexibee_company.flexibee_db_name)

    def _decode(self, data):
        if self.instance._meta.db_table in ['pokladni-pohyb', 'banka']:
            self.invoice = self._get_related_obj(data, 'a')
        elif self.instance._meta.db_table in ['faktura-vydana', 'faktura-prijata']:
            self.payment = self._get_related_obj(data, 'b')
        self.type = data['typVazbyK']
        self.sum = decimal.Decimal(data['castka'])

    def _encode(self):
        data = {}
        data['uhrazovanaFak'] = self.invoice.pk
        data['uhrazovanaFak@type'] = self.invoice._meta.db_table
        data['zbytek'] = self.remain
        return data

    def __unicode__(self):
        return '%s %s' % (self.invoice, self.instance)

    def _delete(self):
        try:
            self.connector.delete(self.payment._meta.db_table, self.payment.pk, {'odparovani': self._encode()})
        except FlexibeeDatabaseException as ex:
            raise ValidationError(ex.errors)

    def _save(self):
        if not self.remain or not self.invoice:
            raise ValidationError('Remain and invoice is required.')

        try:
            if not self.invoice:
                raise ValidationError('Invoice is required.')
            if not self.payment:
                raise ValidationError('Payment is required.')
            self.connector.write(self.payment._meta.db_table, self.payment.pk, {'sparovani': self._encode()})
        except FlexibeeDatabaseException as ex:
            raise ValidationError(ex.errors)


class OptionsLazy(object):

    def __init__(self, name, klass):
        self.name = name
        self.klass = klass

    def __get__(self, instance=None, owner=None):
        option = self.klass(owner)
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
    attachments = ItemsField(Attachment, verbose_name=_('Attachments'), null=True, blank=True, editable=False)

    _flexibee_meta = OptionsLazy('_flexibee_meta', FlexibeeOptions)

    class Meta:
        abstract = True

    class FlexibeeMeta:
        readonly_fields = []

    class RestMeta:
        default_list_fields = ('id',)
