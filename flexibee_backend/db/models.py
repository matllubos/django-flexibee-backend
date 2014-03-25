from django.db.models.fields.related import ForeignKey as DjangoForeignKey, ReverseSingleRelatedObjectDescriptor as DjangoReverseSingleRelatedObjectDescriptor
from django.db import models, router
from django.utils.translation import ugettext_lazy as _
from django.core import exceptions


from flexibee_backend import config



class ReverseSingleRelatedObjectDescriptor(DjangoReverseSingleRelatedObjectDescriptor):

    def get_queryset(self, **db_hints):
        qs = super(ReverseSingleRelatedObjectDescriptor, self).get_queryset(**db_hints)

        if 'instance' in db_hints:
            qs = qs.filter(flexibee_company=db_hints.get('instance').flexibee_company)

        return qs


class CompanyForeignKey(DjangoForeignKey):
    pass


class ForeignKey(DjangoForeignKey):

    def contribute_to_class(self, cls, name, virtual_only=False):
        super(ForeignKey, self).contribute_to_class(cls, name, virtual_only=virtual_only)
        setattr(cls, self.name, ReverseSingleRelatedObjectDescriptor(self))

    def validate(self, value, model_instance):
        if self.rel.parent_link:
            return
        super(DjangoForeignKey, self).validate(value, model_instance)
        if value is None:
            return

        using = router.db_for_read(model_instance.__class__, instance=model_instance)
        qs = self.rel.to._default_manager.using(using).filter(flexibee_company=model_instance.flexibee_company).filter(
                **{self.rel.field_name: value}
             )
        qs = qs.complex_filter(self.rel.limit_choices_to)
        if not qs.exists():
            raise exceptions.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'model': self.rel.to._meta.verbose_name, 'pk': value},
            )


class StoreViaForeignKey(ForeignKey):
    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name


class Company(models.Model):

    flexibee_db_name = models.CharField(verbose_name=_('DB name'), null=False, blank=False, max_length=100,
                                        unique=True)

    class Meta:
        abstract = True

    class FlexibeeMeta:
        mapping = {}


class FlexibeeModel(models.Model):

    flexibee_company = CompanyForeignKey(config.FLEXIBEE_COMPANY_MODEL, editable=False)

    class Meta:
        abstract = True
