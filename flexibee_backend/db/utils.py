from django.db.transaction import get_connection

from flexibee_backend import config


def set_db_name(db_name, backend_name=config.FLEXIBEE_BACKEND_NAME):
    get_connection(backend_name).set_db_name(db_name)
