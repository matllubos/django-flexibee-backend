from django.utils.safestring import mark_safe
from django.forms.widgets import Input

class AttachementWidget(Input):
    input_type = 'file'

    def __init__(self, attachement_manager, *args, **kwargs):
        super(AttachementWidget, self).__init__(*args, **kwargs)
        self.attachement_manager = attachement_manager

    def render(self, name, value, attrs=None):
        out = []
        for attachement in self.attachement_manager.all():
            out.append('<li>%s</li>' % attachement.filename)
        return mark_safe('<ul>%s</ul>%s' % ('\n'.join(out), super(AttachementWidget, self).render(name, None, attrs)))
