from django.db.models.fields.related import ForeignKey
from django.db import models
from django.utils.translation import ugettext_lazy as _

from flexibee_backend import config


class StoreViaForeignKey(ForeignKey):
    def __init__(self, to, db_relation_name=None, *args, **kwargs):
        super(StoreViaForeignKey, self).__init__(to, *args, **kwargs)
        self.db_relation_name = db_relation_name


class Company(models.Model):

    flexibee_db_name = models.CharField(verbose_name=_('DB name'), null=False, blank=False, max_length=100, unique=True)

    class Meta:
        abstract = True

    class FlexibeeMeta:
        mapping = {}


class FlexibeeModel(models.Model):

    class Meta:
        abstract = True
        
        
    def get_form(self, request, obj=None, **kwargs):
        form = super(MyAdmin,self).get_form(self,request, obj,**kwargs)
        # form class is created per request by modelform_factory function
        # so it's safe to modify
        #we modify the the queryset
        form.base_fields['foreign_key_field].queryset = form.base_fields['foreign_key_field].queryset.filter(user=request.user)
        return form
