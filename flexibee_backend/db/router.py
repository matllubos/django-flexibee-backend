from flexibee_backend.models import FlexibeeModel
from flexibee_backend import config


class DatabaseRouter(object):
    def db_for_read(self, model, **hints):
        if issubclass(model, FlexibeeModel):
            return config.FLEXIBEE_BACKEND_NAME
        return 'default'

    def db_for_write(self, model, **hints):
        if issubclass(model, FlexibeeModel):
            return config.FLEXIBEE_BACKEND_NAME

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_syncdb(self, db, model):
        if issubclass(model, FlexibeeModel):
            return False
        return True
