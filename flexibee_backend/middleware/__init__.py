from flexibee_backend.db.utils import reset_connection


class ResetFlexibeeConnection(object):


    def process_exception(self, request, exception):
        """ 
        Reset connection after exception 
        """
        reset_connection()

    def process_response(self, request, response):
        """ 
        Reset connection after response 
        """
        reset_connection()
        return response
