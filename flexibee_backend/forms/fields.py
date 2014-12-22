from django import forms

from flexibee_backend.forms.widgets import BackupFileInput, FILE_INPUT_BACKUP


class BackupFormFielField(forms.FileField):
    widget = BackupFileInput

    def to_python(self, data):
        if data == FILE_INPUT_BACKUP:
            return data
        return super(BackupFormFielField, self).to_python(data)
