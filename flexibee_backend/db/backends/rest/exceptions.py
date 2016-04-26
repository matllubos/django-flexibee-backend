from __future__ import unicode_literals

from django.db.utils import DatabaseError


class FlexibeeDatabaseError(DatabaseError):

    def __init__(self, message=None):
        self.message = message

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return '\n'.join(
            (
                self.__class__.__name__,
                'message: %s' % self.message
            )
        )


class FlexibeeResponseError(Exception):

    def __init__(self, url, resp, message=None):
        super(FlexibeeResponseError, self).__init__(message)
        self.resp = resp
        self.url = url

    def _result_errors(self, data):
        errors = []
        for result in data.get('results', ()):
            for error in result.get('errors'):
                if 'message' in error:
                    errors.append(error.get('message').split('\n')[0])
        return errors

    def __unicode__(self):
        return '\n'.join(
            (
                self.__class__.__name__,
                'message: %s' % self.message,
                'url: %s' % self.url,
                'response status code: %s' % self.resp.status_code,
                'response content: %s' % self.resp.text
            )
        )

    @property
    def errors(self):
        errors = None
        try:
            data = self.resp.json().get('winstrom')
            errors = self._result_errors(data)
        except ValueError:
            pass

        if not errors:
            errors = [self.message]
        return '\n'.join(errors)


class ChangesNotActivatedFlexibeeResponseError(FlexibeeResponseError):

    def __init__(self, url, resp):
        super(ChangesNotActivatedFlexibeeResponseError, self).__init__(url, resp, 'Changes is not activated')


class CompanyDoesNotExistsFlexibeeResponseError(FlexibeeResponseError):

    def __init__(self, url, resp, message, can_reload):
        super(CompanyDoesNotExistsFlexibeeResponseError, self).__init__(url, resp, message)
        self.can_reload = can_reload
