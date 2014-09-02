from django.db.transaction import get_connection

from flexibee_backend import config
from flexibee_backend.db.backends.rest.connection import ModelConnector, AttachmentConnector
from django.conf import settings

MODEL_CONNECTOR = ModelConnector
ATTACHMENT_CONNECTOR = AttachmentConnector


def set_db_name(db_name, backend_name=config.FLEXIBEE_BACKEND_NAME):
    get_connection(backend_name).set_db_name(db_name)


def reset_connection(backend_name=config.FLEXIBEE_BACKEND_NAME):
    get_connection(backend_name).reset()


def str_equal(a, b):
    return str(a) == str(b)


def get_connector(connector, db_name):
    db_settings = settings.DATABASES.get(config.FLEXIBEE_BACKEND_NAME)
    connector = connector(db_settings.get('USER'), db_settings.get('PASSWORD'), db_settings.get('HOSTNAME'))
    connector.db_name = db_name
    return connector
