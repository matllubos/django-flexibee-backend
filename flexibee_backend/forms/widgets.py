from __future__ import unicode_literals

import os

from django.utils.html import conditional_escape, format_html
from django.forms.widgets import CheckboxInput, ClearableFileInput
from django.utils.encoding import force_text
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _


FILE_INPUT_BACKUP = object()


class BackupFileInput(ClearableFileInput):
    template_with_initial = '%(initial_text)s: %(initial)s %(clear_template)s<br />%(backup_template)s'
    template_with_backup = '%(backup)s <label for="%(backup_checkbox_id)s">%(backup_checkbox_label)s</label>'
    template = '%(backup_template)s'
    backup_checkbox_label = _('Backup')
    url_markup_template = '<a href="{0}">{1}</a>'

    def backup_checkbox_name(self, name):
        return name + '-backup'

    def backup_checkbox_id(self, name):
        return name + '_id'

    def render(self, name, value, attrs=None):
        substitutions = {
            'initial_text': self.initial_text,
            'backup_checkbox_label': self.backup_checkbox_label,
            'clear_template': '',
            'clear_checkbox_label': self.clear_checkbox_label,
        }
        backup_checkbox_name = self.backup_checkbox_name(name)
        backup_checkbox_id = self.backup_checkbox_id(backup_checkbox_name)
        substitutions['backup_checkbox_name'] = conditional_escape(backup_checkbox_name)
        substitutions['backup_checkbox_id'] = conditional_escape(backup_checkbox_id)
        substitutions['backup'] = CheckboxInput().render(backup_checkbox_name, False, attrs={'id': backup_checkbox_id})
        substitutions['backup_template'] = self.template_with_backup % substitutions

        template = self.template

        if value and hasattr(value, 'url'):
            template = self.template_with_initial
            substitutions['initial'] = format_html(self.url_markup_template,
                                                   value.url,
                                                   os.path.basename(force_text(value)))
            if not self.is_required:
                checkbox_name = self.clear_checkbox_name(name)
                checkbox_id = self.clear_checkbox_id(checkbox_name)
                substitutions['clear_checkbox_name'] = conditional_escape(checkbox_name)
                substitutions['clear_checkbox_id'] = conditional_escape(checkbox_id)
                substitutions['clear'] = CheckboxInput().render(checkbox_name, False, attrs={'id': checkbox_id})
                substitutions['clear_template'] = self.template_with_clear % substitutions
        return mark_safe(template % substitutions)

    def value_from_datadict(self, data, files, name):
        upload = super(BackupFileInput, self).value_from_datadict(data, files, name)
        if not upload and CheckboxInput().value_from_datadict(data, files, self.backup_checkbox_name(name)):
            return FILE_INPUT_BACKUP
        return upload
