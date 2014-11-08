import string
import random

from django.db import models
from django.db.models.fields.related import ForeignKey
from django.db.models.fields import Field, CharField
from django.core.exceptions import ObjectDoesNotExist
from django.http.response import HttpResponse
from django.utils import timezone

from flexibee_backend.db.utils import (get_connector, get_db_name)
from flexibee_backend.db.backends.rest.connection import ModelConnector
from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseException
from flexibee_backend import config

from calendar import timegm


class CompanyForeignKey(ForeignKey):

    def pre_save(self, model_instance, add):
        """
        Necessary because DB does not set company during insert
        """
        value = getattr(model_instance, self.name)
        if not value:
            setattr(model_instance, self.name, self.rel.to._default_manager.get(flexibee_db_name=get_db_name()))
        return super(CompanyForeignKey, self).pre_save(model_instance, add)


class StoreViaForeignKey(ForeignKey):

    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        kwargs['on_delete'] = models.DO_NOTHING
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name

    def get_internal_type(self):
        return 'StoreViaForeignKey'


class FlexibeeExtKey(CharField):

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 255
        kwargs['db_column'] = 'external-ids'
        super(FlexibeeExtKey, self).__init__(*args, **kwargs)

    def _generate_ext_id(self):
        random_part = ''.join(random.choice(string.digits) for _ in range(10))
        time_part = timegm(timezone.now().timetuple())
        return 'ext:%s:%s%s' % (config.FLEXIBEE_EXTERNAL_KEY_PREFIX, time_part, random_part)

    def get_internal_type(self):
        return 'FlexibeeExtKey'

    def pre_save(self, model_instance, add):
        value = getattr(model_instance, self.attname)
        if not value:
            value = self._generate_ext_id()
            setattr(model_instance, self.attname, value)
        return value

    def to_python(self, value):
        if value and isinstance(value, (list, tuple)):
            for val in value[::-1]:
                if val.startswith('ext:%s' % self.prefix):
                    return val
        return value


class RemoteFile(object):

    def __init__(self, instance, field):
        self.instance = instance
        self.field = field

    def __unicode__(self):
        return '.'.join((self.instance.pk, self.field.type)) if self.instance else None

    @property
    def file_response(self):
        if not self.instance.pk:
            raise AttributeError('The object musth have set id.')

        connector = get_connector(ModelConnector, self.instance.flexibee_company.flexibee_db_name)
        r = connector.get_response(self.instance._meta.db_table, self.instance.pk, self.field.type)
        return HttpResponse(r.content, content_type=r.headers['content-type'])


class ItemsManager(object):
    _connector = None

    def __init__(self, instance, item_class):
        self.instance = instance
        self.item_class = item_class

    @property
    def connector(self):
        if self.instance.pk and self._connector is None:
            self._connector = get_connector(self.item_class.connector_class,
                                            self.instance.flexibee_company.flexibee_db_name)
        return self._connector

    def all(self):
        if not self.instance.pk:
            return []

        data = self.connector.read(self.instance._meta.db_table, self.instance.pk)

        items_list = []
        for items_data in data:
            attachment = self.item_class(self.instance, self.connector, data=items_data)
            items_list.append(attachment)
        return items_list

    def create(self, **kwargs):
        if not self.instance.pk:
            raise FlexibeeDatabaseException('You cannot create item of not saved instance')

        item = self.add(**kwargs)
        item.save()
        return item

    def delete(self):
        if not self.instance.pk:
            raise FlexibeeDatabaseException('You cannot Delete items of not saved instance')
        for item in self.all():
            item.delete()

    def add(self, **kwargs):
        if not self.instance.pk:
            raise FlexibeeDatabaseException('You cannot add item to not saved instance')

        return self.item_class(self.instance, self.connector, **kwargs)

    def get(self, pk):
        if not self.instance.pk:
            raise ObjectDoesNotExist

        data = self.connector.read(self.instance._meta.db_table, self.instance.pk, pk)
        if not data:
            raise ObjectDoesNotExist
        return self.item_class(data=data[0], instance=self.instance,
                               connector=self.connector)


class RemoteFileDescriptor(object):

    def __init__(self, field):
        self.field = field

    def __get__(self, instance=None, owner=None):
        if instance is None:
            raise AttributeError(
                'The "%s" attribute can only be accessed from %s instances.'
                % (self.field.name, owner.__name__))

        attr = RemoteFile(instance, self.field)
        instance.__dict__[self.field.name] = attr
        return instance.__dict__[self.field.name]

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value


class ItemsDescriptor(object):

    items_class = None

    def __init__(self, field, item_class):
        self.field = field
        self.item_class = item_class

    def __get__(self, instance=None, owner=None):
        if instance is None:
            raise AttributeError(
                'The "%s" attribute can only be accessed from %s instance.'
                % (self.field.name, owner.__name__))

        attr = self.item_class.manager(instance, self.item_class)
        instance.__dict__[self.field.name] = attr
        return instance.__dict__[self.field.name]

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value


class RemoteFileField(Field):

    def __init__(self, verbose_name=None, name=None, type=None, **kwargs):
        super(RemoteFileField, self).__init__(verbose_name=verbose_name, name=name, **kwargs)
        self.type = type

    def contribute_to_class(self, cls, name):
        super(RemoteFileField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, RemoteFileDescriptor(self))


class ItemsField(Field):

    def __init__(self, item_class, *args, **kwargs):
        kwargs['editable'] = False
        super(ItemsField, self).__init__(*args, **kwargs)
        self.item_class = item_class

    def contribute_to_class(self, cls, name):
        super(ItemsField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, ItemsDescriptor(self, self.item_class))

    def formfield(self, **kwargs):
        return None
