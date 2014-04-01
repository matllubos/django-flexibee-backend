from django.db.models.fields.related import ForeignKey
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.text import slugify
from django.db.models.fields import Field
from django.db.transaction import get_connection

from flexibee_backend import config
from django.db.models.fields.files import FileField


FileField

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
    def read(self):
        print get_connection(config.FLEXIBEE_BACKEND_NAME).connector.download_file(self.instance._meta.db_table,
                                                                                   self.instance.pk, self.field.type)


class RemoteFileDescriptor(object):

    def __init__(self, field):
        self.field = field

    def __get__(self, instance=None, owner=None):
        if instance is None:
            raise AttributeError(
                "The '%s' attribute can only be accessed from %s instances."
                % (self.field.name, owner.__name__))

        attr = RemoteFile(instance, self.field)
        instance.__dict__[self.field.name] = attr

        # print get_connection(config.FLEXIBEE_BACKEND_NAME).connector.download_file(instance._meta.db_table,
        #                                                                           instance.pk, self.field.type)
        # That was fun, wasn't it?
        return instance.__dict__[self.field.name]

    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value


class RemoteFileField(Field):

    def __init__(self, verbose_name=None, name=None, type=None, **kwargs):
        super(RemoteFileField, self).__init__(verbose_name=verbose_name, name=name, **kwargs)
        self.type = type

    @property
    def set_connection(self):
        pass

    def contribute_to_class(self, cls, name):
        print 'ted'
        print cls._meta.db_table
        super(RemoteFileField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, RemoteFileDescriptor(self))


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
        readonly_fields = []


class FlexibeeModel(models.Model):

    flexibee_company = CompanyForeignKey(config.FLEXIBEE_COMPANY_MODEL, null=True, blank=True, editable=False,
                                         on_delete=models.DO_NOTHING)

    class Meta:
        abstract = True
