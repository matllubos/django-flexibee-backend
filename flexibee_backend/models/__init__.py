import decimal
from datetime import timedelta

from .fields import *

from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _
from django.db.models.base import ModelBase
from django.utils.functional import SimpleLazyObject
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile

from chamber.utils.datastructures import ChoicesNumEnum, ChoicesEnum

from flexibee_backend.db.backends.rest.utils import db_name_validator
from flexibee_backend.db.backends.rest.admin_connection import admin_connector
from flexibee_backend.db.backends.rest.connection import AttachmentConnector, RelationConnector
from flexibee_backend.models.utils import get_model_by_db_table, lazy_obj_loader
from flexibee_backend.db.backends.rest.exceptions import FlexibeeResponseError
from flexibee_backend.tasks import synchronize_company
import time


class FlexibeeItem(object):
    """
    Class which represents model for objects which is firmly connected to other real db model
    """

    connector_class = None
    is_stored = False
    manager = ItemsManager

    def __init__(self, instance, connector, data=None, **kwargs):
        self.instance = instance
        self._foreign_key_setter('instance', instance)
        self.connector = connector
        if data is not None:
            self.stored = True
            self._decode(data)

        for key, value in kwargs.items():
            setattr(self, key, value)

    def _foreign_key_setter(self, field_name, rel_obj_or_class=None, rel_pk=None):
        if rel_obj_or_class and isinstance(rel_obj_or_class, models.Model):
            rel_obj = rel_obj_or_class
            rel_pk = rel_obj_or_class.pk
            model = rel_obj_or_class.__class__
        elif rel_obj_or_class and rel_pk and issubclass(rel_obj_or_class, models.Model):
            rel_obj = lazy_obj_loader(rel_obj_or_class, {'pk':rel_pk}, self.instance.flexibee_company.flexibee_db_name)
            model = rel_obj_or_class
        else:
            model = None
            rel_obj = None
        setattr(self, field_name, rel_obj)
        setattr(self, '%s_id' % field_name, rel_pk)
        setattr(self, '%s_model' % field_name, model)

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

    @property
    def id(self):
        return getattr(self, 'pk')

    def delete(self):
        self._delete()
        self.is_stored = False

    def save(self):
        self.validate()
        self._save()
        self.is_stored = True

    def _update_via(self):
        return self.instance

    # TODO: validation should be better for future
    def validate(self):
        """
        Should contains pre_save validation, this is more for developers than for users,
        input data should be valid
        """
        pass

    def _delete(self):
        """
        There may be changed code which implements calls connector for deleting object
        """
        try:
            update_via = self._update_via()
            self.connector.delete(update_via._meta.db_table, update_via.pk, self.pk)
        except FlexibeeResponseError as ex:
            raise ValidationError(ex.errors)

    def _save(self):
        """
        There may be changed code which implements calls connector for creating or updating object
        """
        try:
            update_via = self._update_via()
            self.pk = self.connector.write(update_via._meta.db_table, update_via.pk, self._encode())
        except FlexibeeResponseError as ex:
            raise ValidationError(ex.errors)

    def __str__(self):
        return self.__unicode__()


class Attachment(FlexibeeItem):
    """
    Attachements for all flexibee objects
    """

    connector_class = AttachmentConnector

    filename = None
    file = None
    content_type = None
    description = None
    link = None
    pk = None

    def _decode(self, data):
        self.pk = data.get('id')
        self.filename = data.get('nazSoub')
        self.content_type = data.get('contentType', 'content/unknown')
        self.link = data.get('link')
        self.description = data.get('poznam')

    def _encode(self):
        data = {'poznam': self.description, 'link': self.link, 'nazSoub': self.filename}
        if not self.pk:
            data['file'] = self.file
            data['contentType'] = self.content_type
        else:
            data['pk'] = self.pk
        return data

    def __unicode__(self):
        return self.filename

    def validate(self):
        errors = {}
        if self.is_stored and not self.file:
            errors['file'] = _('File must be set for creation.')

        if not self.filename:
            errors['filename'] = _('Filename must be set')

        if errors:
            raise ValidationError(errors)

    @property
    def file_response(self):
        if not self.instance or not self.connector:
            raise AttributeError('The %s attachment must be firstly stored.' % (self.filename))

        update_via = self._update_via()
        r = self.connector.get_response(update_via._meta.db_table, update_via.pk, self.pk)
        return HttpResponse(r.content, content_type=r.headers['content-type'])


class RelationManager(ItemsManager):

    def delete(self):
        if not self.instance.pk:
            raise FlexibeeDatabaseError('You cannot Delete items of not saved instance')

        if self.instance._meta.db_table in ['pokladni-pohyb', 'banka']:
            self.connector.delete(self.instance._meta.db_table, self.instance.pk, [])
        else:
            super(RelationManager, self).delete()


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
    sum = None
    currency_sum = None
    pk = None

    manager = RelationManager

    def __init__(self, instance, connector, data=None, **kwargs):
        super(Relation, self).__init__(instance, connector, data, **kwargs)
        if self.instance._meta.db_table in ['pokladni-pohyb', 'banka']:
            self._foreign_key_setter('payment', instance)
        elif self.instance._meta.db_table in ['faktura-vydana', 'faktura-prijata']:
            self._foreign_key_setter('invoice', instance)

    def _get_related_db_table(self, data, data_field_name):
        return data['%s@ref' % data_field_name].split('/')[-2]

    def _get_related_pk(self, data, data_field_name):
        return data['%s@ref' % data_field_name].split('/')[-1][:-5]

    def _set_related_obj(self, data, data_field_name, field_name):
        related_model = get_model_by_db_table(self._get_related_db_table(data, data_field_name))
        return self._foreign_key_setter(field_name, related_model, self._get_related_pk(data, data_field_name))

    def _decode(self, data):
        if self.instance._meta.db_table in ['pokladni-pohyb', 'banka']:
            self._set_related_obj(data, 'a', 'invoice')
        elif self.instance._meta.db_table in ['faktura-vydana', 'faktura-prijata']:
            self._set_related_obj(data, 'b', 'payment')
        self.type = data['typVazbyK']
        self.pk = data['id']
        self.sum = decimal.Decimal(data['castka'])
        if 'castkaMen' in data:
            self.currency_sum = decimal.Decimal(data['castkaMen'])

    def _encode(self):
        data = {}
        data['uhrazovanaFak'] = self.invoice.pk
        data['uhrazovanaFak@type'] = self.invoice._meta.db_table
        data['zbytek'] = self.remain
        return data

    def __unicode__(self):
        return 'Invoice: %s Payment: %s, %s' % (self.invoice, self.payment, self.currency_sum)

    def _delete(self):
        """
        Rewritten delete because it needs data for delete relation via payment
        """

        try:
            update_via = self._update_via()
            if update_via is None:
                raise ValidationError(_('Relation without payment cannot be deleted.'))

            self.connector.delete(update_via._meta.db_table, update_via.pk, self._encode())
        except FlexibeeResponseError as ex:
            raise ValidationError(ex.errors)

    def _update_via(self):
        return self.payment

    def validate(self):
        if self.is_stored:
            raise ValidationError(_('Existing relation cannot be changed.'))

        errors = {}
        if not self.remain:
            errors['remain'] = _('Remain is required.')
        if not self.invoice:
            errors['invoice'] = _('Invoice is required.')
        if not self.payment:
            errors['payment'] = _('Payment is required.')

        if errors:
            raise ValidationError(errors)


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
        models = [b for b in self.model.__mro__ if issubclass(b, (FlexibeeModel, Company))]
        for model in models:
            value = getattr(model.FlexibeeMeta, name, None)
            if value is not None:
                return value


class Company(models.Model):

    FLEXIBEE_STATE = ChoicesNumEnum(
        ('DETACHED', _('Detached')),
        ('ATTACHED', _('Attached')),
    )

    FLEXIBEE_SYNCHRONIZATION_STATE = ChoicesEnum(
        ('SYNCHRONIZED', _('Synchronized')),
        ('DETACHED', _('Detached')),
        ('ERROR', _('Synchronization error')),
        ('SYNCHRONIZING', _('Synchronizing')),
    )

    # TODO: should be partly unique
    flexibee_db_name = models.CharField(verbose_name=_('DB name'), null=True, blank=True, max_length=100,
                                        validators=[db_name_validator])
    flexibee_synchronization_start = models.DateTimeField(verbose_name=_('Synchronization start'), null=True, blank=True,
                                                         editable=False)
    flexibee_last_synchronization = models.DateTimeField(verbose_name=_('Last synchronization'), null=True, blank=True,
                                                         editable=False)
    flexibee_state = models.PositiveIntegerField(
        verbose_name=_('Flexibee state'), choices=FLEXIBEE_STATE.choices, default=FLEXIBEE_STATE.DETACHED, null=False,
        blank=False, editable=False
    )

    _flexibee_meta = OptionsLazy('_flexibee_meta', FlexibeeOptions)

    def __init__(self, *args, **kwargs):
        super(Company, self).__init__(*args, **kwargs)
        self._exists = None

    def flexibee_create(self):
        admin_connector.create_company(self)

    def flexibee_update(self):
        admin_connector.update_company(self)

    def save(self, synchronized=False, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if synchronized:
            self.flexibee_synchronization_start = None
            self.flexibee_last_synchronization = timezone.now()
            self.flexibee_state = self.FLEXIBEE_STATE.ATTACHED
        else:
            self.flexibee_state = self.FLEXIBEE_STATE.DETACHED
        super(Company, self).save(force_insert, force_update, using, update_fields)

    @property
    def exists(self):
        if self._exists is None:
            self._exists = admin_connector.exists_company(self)
        return self._exists

    def synchronize(self):
        self.flexibee_synchronization_start = timezone.now()
        self.save()
        synchronize_company.delay(self.pk)

    @property
    def synchronization_state(self):
        if self.flexibee_state == self.FLEXIBEE_STATE.ATTACHED:
            return self.FLEXIBEE_SYNCHRONIZATION_STATE.SYNCHRONIZED
        elif not self.flexibee_synchronization_start:
            return self.FLEXIBEE_SYNCHRONIZATION_STATE.DETACHED
        elif self.flexibee_synchronization_start + timedelta(minutes=500) < timezone.now():
            return self.FLEXIBEE_SYNCHRONIZATION_STATE.ERROR
        else:
            return self.FLEXIBEE_SYNCHRONIZATION_STATE.SYNCHRONIZING

    def synchronization_state_display(self):
        return self.FLEXIBEE_SYNCHRONIZATION_STATE.get_label(self.synchronization_state)
    synchronization_state_display.short_description = _('Flexibee state')

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
    flexibee_ext_id = FlexibeeExtKey(null=False, blank=False, editable=False, db_column='external-ids')

    _flexibee_meta = OptionsLazy('_flexibee_meta', FlexibeeOptions)
    _internal_obj_cache = None

    @property
    def internal_obj(self):
        if not self._internal_obj_cache:
            self._internal_obj_cache = self._internal_model.objects.get(flexibee_company=self.flexibee_company,
                                                                        flexibee_obj_id=self.pk)
            self._internal_obj_cache._flexibee_obj_cache = self
        return self._internal_obj_cache

    class Meta:
        abstract = True

    class FlexibeeMeta:
        readonly_fields = []
        readonly = False
        view = False

    class RestMeta:
        default_general_fields = ('id',)
