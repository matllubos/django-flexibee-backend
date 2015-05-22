import string
import random

from copy import deepcopy

from django.db import models
from django.db.models.fields.related import ForeignKey, OneToOneField
from django.db.models.fields import Field, CharField, FieldDoesNotExist
from django.core.exceptions import ObjectDoesNotExist
from django.http.response import HttpResponse
from django.utils import timezone, translation
from django.core import exceptions

from flexibee_backend.db.utils import get_connector, get_db_name, set_db_name
from flexibee_backend.db.backends.rest.connection import ModelConnector
from flexibee_backend.db.backends.rest.exceptions import FlexibeeDatabaseError
from flexibee_backend import config

from calendar import timegm
from chamber.models.fields import FileField
from flexibee_backend.forms.fields import BackupFormFielField
from flexibee_backend.forms.widgets import FILE_INPUT_BACKUP


class InternalModel(models.Model):

    flexibee_obj_id = models.PositiveIntegerField(null=False, blank=False, editable=False)
    flexibee_company = models.ForeignKey(config.FLEXIBEE_COMPANY_MODEL, null=False, blank=False, editable=False)

    _flexibee_obj_cache = None

    @property
    def flexibee_obj(self):
        if not self._flexibee_obj_cache:
            db_name_cache = get_db_name()
            set_db_name(self.flexibee_company.flexibee_db_name)
            self._flexibee_obj_cache = self._flexibee_model.objects.get(pk=self.flexibee_obj_id)
            self._flexibee_obj_cache._internal_obj_cache = self
            set_db_name(db_name_cache)
        return self._flexibee_obj_cache

    class Meta:
        abstract = True
        unique_together = ('flexibee_obj_id', 'flexibee_company')


def create_internal_db(cls):
    internal_fields = ()

    if hasattr(cls, 'FlexibeeMeta'):
        internal_fields = cls.FlexibeeMeta.__dict__.pop('internal_fields', ())
    parents = []

    all_internal_fields = list(internal_fields)
    for base in cls.__bases__:
        if hasattr(base, '_internal_model') and base._internal_model:
            parents.append(base._internal_model)
            all_internal_fields += base._internal_fields

    cls._internal_fields = all_internal_fields

    fields = {}

    for field_name in internal_fields:
        try:
            field = cls._meta.get_field(field_name)
            field.order_by = False
            fields[field_name] = deepcopy(field)
            if hasattr(fields[field_name], 'rel') and fields[field_name].rel:
                fields[field_name].rel.related_name = 'internal_%s' % (fields[field_name].rel.related_name or '+')

        except FieldDoesNotExist:
            pass

    if fields or parents:
        name = '%sInternal' % cls.__name__
        meta = type('Meta', (object,), {
            'abstract': cls._meta.abstract
        })

        cls_kwargs = fields.copy()
        cls_kwargs['Meta'] = meta
        cls_kwargs['__module__'] = cls.__module__
        cls_kwargs['_flexibee_model'] = cls

        parents = parents or (InternalModel,)
        return type(str(name), tuple(parents), cls_kwargs)


class SouthFieldMixin(object):

    def south_field_triple(self):
        from south.modelsinspector import introspector
        cls_name = '%s.%s' % (self.__class__.__module__ , self.__class__.__name__)
        args, kwargs = introspector(self)
        return (cls_name, args, kwargs)


class CompanyForeignKey(SouthFieldMixin, ForeignKey):

    def contribute_to_class(self, cls, name, virtual_only=False):
        setattr(cls, '_internal_model', create_internal_db(cls))
        super(CompanyForeignKey, self).contribute_to_class(cls, name, virtual_only=virtual_only)

    def pre_save(self, model_instance, add):
        """
        Necessary because DB does not set company during insert
        """
        value = getattr(model_instance, self.name)
        if not value:
            setattr(model_instance, self.name, self.rel.to._default_manager.get(flexibee_db_name=get_db_name()))
        return super(CompanyForeignKey, self).pre_save(model_instance, add)


class StoreViaForeignKey(SouthFieldMixin, ForeignKey):

    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        kwargs['on_delete'] = models.DO_NOTHING
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name

    def get_internal_type(self):
        return 'StoreViaForeignKey'


class FlexibeeExtKey(SouthFieldMixin, CharField):

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
                if val.startswith('ext:%s' % config.FLEXIBEE_EXTERNAL_KEY_PREFIX):
                    return val
        return value


class RemoteFile(object):

    def __init__(self, instance, field):
        self.instance = instance
        self.field = field

    def __unicode__(self):
        return '.'.join((self.instance.pk, self.field.type)) if self.instance else None

    @property
    def language_code(self):
        lang_code = translation.get_language()
        if not lang_code in config.FLEXIBEE_PDF_REPORT_AVAILABLE_LANGUAGES:
            lang_code = config.FLEXIBEE_PDF_REPORT_DEFAULT_LANGUAGE
        return lang_code

    @property
    def file_response(self):
        if not self.instance.pk:
            raise AttributeError('The object musth have set id.')
        connector = get_connector(ModelConnector, self.instance.flexibee_company.flexibee_db_name)
        query_string = 'report-lang=%s' % self.language_code
        r = connector.get_response(self.instance._meta.db_table, self.instance.pk, self.field.type, query_string)
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
            raise FlexibeeDatabaseError('You cannot create item of not saved instance')

        item = self.add(**kwargs)
        item.save()
        return item

    def delete(self):
        if not self.instance.pk:
            raise FlexibeeDatabaseError('You cannot Delete items of not saved instance')
        for item in self.all():
            item.delete()

    def add(self, **kwargs):
        if not self.instance.pk:
            raise FlexibeeDatabaseError('You cannot add item to not saved instance')

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


class RemoteFileField(SouthFieldMixin, Field):

    def __init__(self, verbose_name=None, name=None, type=None, **kwargs):
        super(RemoteFileField, self).__init__(verbose_name=verbose_name, name=name, **kwargs)
        self.type = type

    def contribute_to_class(self, cls, name):
        super(RemoteFileField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, RemoteFileDescriptor(self))


class ItemsField(SouthFieldMixin, Field):

    def __init__(self, item_class=None, *args, **kwargs):
        kwargs['editable'] = False
        super(ItemsField, self).__init__(*args, **kwargs)
        self.item_class = item_class

    def contribute_to_class(self, cls, name):
        super(ItemsField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, ItemsDescriptor(self, self.item_class))

    def formfield(self, **kwargs):
        return None


class CrossDatabaseForeignKeyMixin(SouthFieldMixin):

    def validate(self, value, model_instance):
        if self.rel.parent_link:
            return
        super(ForeignKey, self).validate(value, model_instance)
        if value is None:
            return

        qs = self.rel.to._default_manager.filter(
            **{self.rel.field_name: value}
        )
        qs = qs.complex_filter(self.rel.limit_choices_to)
        if not qs.exists():
            raise exceptions.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'model': self.rel.to._meta.verbose_name, 'pk': value},
            )


class CrossDatabaseForeignKey(CrossDatabaseForeignKeyMixin, ForeignKey):
    pass


class CrossDatabaseOneToOneField(CrossDatabaseForeignKeyMixin, OneToOneField):
    pass


class BackupFileField(FileField):

    def formfield(self, form_class=None, choices_form_class=None, **kwargs):
        defaults = {'form_class': BackupFormFielField}
        defaults.update(kwargs)
        return super(BackupFileField, self).formfield(**defaults)

    def clean(self, value, model_instance):
        if value == FILE_INPUT_BACKUP:
            model_instance._flexibee_backup = True
            return None
        return super(BackupFileField, self).clean(value, model_instance)
