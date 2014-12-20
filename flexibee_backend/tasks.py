from celery import Celery

from django.db.models.loading import get_model

from flexibee_backend.config import FLEXIBEE_COMPANY_MODEL
from flexibee_backend.db.backends.rest.admin_connection import admin_connector
from django.utils import timezone
import time

app = Celery()


@app.task()
def synchronize_company(company_pk):
    Company = get_model(*FLEXIBEE_COMPANY_MODEL.split('.', 1))
    company = Company._default_manager.get(pk=company_pk)
    time.sleep(20)
    if company.exists:
        print 'update'
        admin_connector.update_company(company)
    else:
        print 'creating'
        admin_connector.create_company(company)
        admin_connector.update_company(company)
    company.save(synchronized=True)

