from django.db.models.fields.related import ForeignKey
from django.db.models.fields import Field
from django.core.exceptions import ObjectDoesNotExist
from django.http.response import HttpResponse

from flexibee_backend.db.utils import (get_connector, get_db_name)
from flexibee_backend.db.backends.rest.connection import ModelConnector


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
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name


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
        if self._connector is None:
            self._connector = get_connector(self.item_class.connector_class,
                                            self.instance.flexibee_company.flexibee_db_name)
        return self._connector

    def all(self):
        data = self.connector.read(self.instance._meta.db_table, self.instance.pk)

        items_list = []
        for items_data in data:
            attachment = self.item_class(self.instance, self.connector, data=items_data)
            items_list.append(attachment)
        return items_list

    def create(self, **kwargs):
        item = self.add(**kwargs)
        item.save()
        return item

    def add(self, **kwargs):
        return self.item_class(self.instance, self.connector, **kwargs)

    def get(self, pk):
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

        attr = ItemsManager(instance, self.item_class)
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
