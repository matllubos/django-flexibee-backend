from django.db.models.fields.related import ForeignKey, ManyToManyField
from django.db.transaction import get_connection
from django.db.models.fields import Field

from django.http.response import HttpResponse

from flexibee_backend import config
from flexibee_backend.db import fields as flexibee_fields
from django.forms.models import ModelForm

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

        r = get_connection(config.FLEXIBEE_BACKEND_NAME).connector.file_response(self.instance._meta.db_table,
                                                                                 self.instance.pk, self.field.type)
        return HttpResponse(r.content, content_type=r.headers['content-type'])

    def __unicode__(self):
        return '.'.join((self.instance.pk, self.field.type)) if self.instance else None


class Attachment(object):

    def __init__(self, filename=None, pk=None, file=None, content_type=None, instance=None):
        self.filename = filename
        self.pk = pk
        self.file = file
        self.content_type = content_type
        self.instance = instance

    def __unicode__(self):
        return self.filename

    def __str__(self):
        return self.filename

    def delete(self):
        print self.instance
        if not self.instance:
            raise AttributeError('The %s attachement can only be deleted from instances.' % (self.filename))
        get_connection(config.FLEXIBEE_BACKEND_NAME).connector.delete_attachement(self.instance._meta.db_table,
                                                                                  self.instance.pk, self.pk)

    @property
    def file_response(self):
        if not self.instance:
            raise AttributeError('The object musth have set id.')

        r = get_connection(config.FLEXIBEE_BACKEND_NAME).connector.get_attachement_content(self.instance._meta.db_table,
                                                                                           self.instance.pk, self.pk)
        return HttpResponse(r.content, content_type=r.headers['content-type'])


class Attachements(object):
    
    def __init__(self, instance):
        self.instance = instance

    def all(self):
        data = get_connection(config.FLEXIBEE_BACKEND_NAME).connector.get_attachements(self.instance._meta.db_table,
                                                                                                   self.instance.pk)
        attachement_list = []
        for attachement_data in data:
            attachement = Attachment(filename=attachement_data.get('nazSoub'), pk=attachement_data.get('id'),
                                               content_type=attachement_data.get('contentType'), instance=self.instance)
            attachement_list.append(attachement)
        return attachement_list
        
    def add(self, attachement):
        get_connection(config.FLEXIBEE_BACKEND_NAME).connector.create_attachement(self.instance._meta.db_table,
                                                                                  self.instance.pk, attachement.filename, 
                                                                                  attachement.file)


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
        print kwargs
        defaults = {'form_class': flexibee_fields.AttachementsField, 'atachement_manager': AttachementsDescriptor(self)}
        defaults.update(kwargs)
        return super(AttachmentsField, self).formfield(**defaults)
    
    def value_from_object(self, obj):
        """
        Returns the value of this field in the given model instance.
        """
        return getattr(obj, self.attname)
    
