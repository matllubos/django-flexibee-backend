from django.db.models.fields.related import ForeignKey
from django.db.models.fields import Field
from django.core.exceptions import ObjectDoesNotExist
from django.http.response import HttpResponse

from flexibee_backend.db.utils import get_connector, MODEL_CONNECTOR, ATTACHEMENT_CONNECTOR


class CompanyForeignKey(ForeignKey):
    pass


class StoreViaForeignKey(ForeignKey):
    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name


class RemoteFile(object):

    def __init__(self, instance, field):
        self.instance = instance
        self.field = field

    @property
    def file_response(self):
        if not self.instance.pk:
            raise AttributeError('The object musth have set id.')

        connector = get_connector(MODEL_CONNECTOR, self.instance.flexibee_company.flexibee_db_name)
        r = connector.get_response(self.instance._meta.db_table, self.instance.pk, self.field.type)
        return HttpResponse(r.content, content_type=r.headers['content-type'])

    def __unicode__(self):
        return '.'.join((self.instance.pk, self.field.type)) if self.instance else None


class Attachement(object):

    def __init__(self, filename, content_type, file=None, pk=None, instance=None, connector=None):
        self.filename = filename
        self.pk = pk
        self.file = file
        self.content_type = content_type
        self.instance = instance
        self.connector = connector

    def __unicode__(self):
        return self.filename

    def __str__(self):
        return self.filename

    def delete(self):
        if not self.instance:
            raise AttributeError('The %s attachement must be firstly stored.' % (self.filename))
        connector = get_connector(ATTACHEMENT_CONNECTOR, self.instance.flexibee_company.flexibee_db_name)
        connector.delete(self.instance._meta.db_table, self.instance.pk, self.pk)

    @property
    def file_response(self):
        if not self.instance:
            raise AttributeError('The %s attachement must be firstly stored.' % (self.filename))

        connector = get_connector(ATTACHEMENT_CONNECTOR, self.instance.flexibee_company.flexibee_db_name)
        r = connector.get_response(self.instance._meta.db_table, self.instance.pk, self.pk)
        return HttpResponse(r.content, content_type=r.headers['content-type'])


class Attachements(object):

    def __init__(self, instance):
        self.instance = instance
        self.connector = get_connector(ATTACHEMENT_CONNECTOR, self.instance.flexibee_company.flexibee_db_name)

    def all(self):
        data = self.connector.read(self.instance._meta.db_table, self.instance.pk)

        attachement_list = []
        for attachement_data in data:
            attachement = Attachement(attachement_data.get('nazSoub'), attachement_data.get('contentType'),
                                      pk=attachement_data.get('id'), instance=self.instance,
                                      connector=self.connector)
            attachement_list.append(attachement)
        return attachement_list

    def create(self, attachement):
        if not attachement.file:
            raise AttributeError('New %s attachement must have set file.' % (self.filename))

        self.connector.write(self.instance._meta.db_table, self.instance.pk, attachement.filename, attachement.file,
                             attachement.content_type)

    def get(self, pk):
        data = self.connector.read(self.instance._meta.db_table, self.instance.pk, pk)
        if not data:
            raise ObjectDoesNotExist
        data = data[0]
        return Attachement(data.get('nazSoub'), data.get('contentType'), pk=data.get('id'),
                           instance=self.instance, connector=self.connector)


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


class AttachementsDescriptor(object):

    def __init__(self, field):
        self.field = field

    def __get__(self, instance=None, owner=None):
        if instance is None:
            raise AttributeError(
                'The "%s" attribute can only be accessed from %s instances.'
                % (self.field.name, owner.__name__))

        attr = Attachements(instance)
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


class AttachmentsField(Field):

    def contribute_to_class(self, cls, name):
        super(AttachmentsField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, AttachementsDescriptor(self))

    def formfield(self, **kwargs):
        return None
