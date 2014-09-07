from django.db import models
from django.utils.functional import SimpleLazyObject
from flexibee_backend.db.utils import get_db_name, set_db_name


def get_model_by_db_table(db_table):
    for model in models.get_models():
        if model._meta.db_table == db_table:
            return model


def load_object(model, pk, db_name):
    if db_name:
        old_db_name = get_db_name()
        set_db_name(db_name)
        obj = model._default_manager.get(**filter)
        set_db_name(old_db_name)
    else:
        obj = model.objects.get(pk=pk)
    return obj


def lazy_obj_loader(model, filter, db_name=None):
    return SimpleLazyObject(lambda:load_object(model, filter, db_name))
