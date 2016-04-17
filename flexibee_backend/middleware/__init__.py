from django.http import HttpResponseRedirect

from flexibee_backend.db.utils import reset_connection
from flexibee_backend.db.backends.rest.exceptions import CompanyDoesNotExistsFlexibeeResponseError
from flexibee_backend.config import FLEXIBEE_RELOAD_TO_IF_COMPANY_DOES_NOT_EXISTS


class ResetFlexibeeConnection(object):

    def process_exception(self, request, exception):
        """
        Reset connection after exception 
        """
        reset_connection()
        if (isinstance(exception, CompanyDoesNotExistsFlexibeeResponseError) and exception.can_reload and
                FLEXIBEE_RELOAD_TO_IF_COMPANY_DOES_NOT_EXISTS):
            return HttpResponseRedirect(FLEXIBEE_RELOAD_TO_IF_COMPANY_DOES_NOT_EXISTS)

    def process_response(self, request, response):
        """
        Reset connection after response 
        """
        reset_connection()
        return response
