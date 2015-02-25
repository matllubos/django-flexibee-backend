from celery import Celery

from django.core.files.uploadhandler import TemporaryFileUploadHandler

from flexibee_backend.config import FLEXIBEE_COMPANY_MODEL
from flexibee_backend.db.backends.rest.admin_connection import admin_connector


app = Celery()
app.config_from_object('django.conf:settings')


@app.task()
def synchronize_company(company_pk, backup=False, callback=None):
    from django.db.models.loading import get_model

    Company = get_model(*FLEXIBEE_COMPANY_MODEL.split('.', 1))
    company = Company._default_manager.get(pk=company_pk)
    if company.exists:
        print 'update'
        admin_connector.update_company(company)
    else:
        print 'creating'
        admin_connector.create_company(company)
        admin_connector.update_company(company)

    if backup:
        handler = TemporaryFileUploadHandler()
        handler.new_file('flexibee_backup', '%s.winstrom-backup' % company.flexibee_db_name,
                         'application/x-winstrom-backup', 0, 'utf-8')

        setattr(company, 'flexibee_backup',
                admin_connector.backup_company(company, handler)
                )
    company.save(synchronized=True)

    if callback:
        if not isinstance(callback, (list, tuple, set)):
            callback = [callback]

        for method in callback:
            getattr(company, method)()

