from django.db.transaction import get_connection
from django.conf import settings

from flexibee_backend import config


def set_db_name(db_name, backend_name=config.FLEXIBEE_BACKEND_NAME):
    get_connection(backend_name).set_db_name(db_name)


def get_db_name(backend_name=config.FLEXIBEE_BACKEND_NAME):
    return get_connection(backend_name).get_db_name()


def reset_connection(backend_name=config.FLEXIBEE_BACKEND_NAME):
    from flexibee_backend.db.backends.rest.admin_connection import admin_connector

    get_connection(backend_name).reset()
    admin_connector.reset()


def str_equal(a, b):
    return str(a) == str(b)


def get_connector(connector, db_name):
    db_settings = settings.DATABASES.get(config.FLEXIBEE_BACKEND_NAME)
    connector = connector(db_settings.get('USER'), db_settings.get('PASSWORD'), db_settings.get('HOSTNAME'))
    connector.db_name = db_name
    return connector
