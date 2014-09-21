from django.forms.formsets import BaseFormSet

from is_core.forms.formsets import BaseFormSetMixin


class ItemBaseFormSet(BaseFormSetMixin, BaseFormSet):
    """
    Formset which is very similar to models.BaseInlineFormSet. But there is no model. 
    Must be used with special ItemForm which contains save method
    """

    def __init__(self, instance=None, queryset=None, *args, **kwargs):
        """
        instance == parent of instances inside queryset
        """
        self.instance = instance
        self.queryset = queryset
        super(ItemBaseFormSet, self).__init__(*args, **kwargs)

    def total_form_count(self):
        """
        Returns the total number of forms in this FormSet.
        Number of forms depends on number of records inside queryset
        """
        total_form_count = super(ItemBaseFormSet, self).total_form_count()
        if self.is_bound:
            return total_form_count
        return total_form_count + len(self.queryset)

    def save(self, commit=True):
        self.deleted_objects = []
        forms_to_delete = self.deleted_forms
        out = []
        for form in self.forms:
            if form in forms_to_delete:
                if form.instance:
                    self.deleted_objects.append(form.instance)
                    if commit:
                        form.instance.delete()
            elif form.has_changed():
                out.append(form.save(commit=commit))
        return out

    def _construct_form(self, i, **kwargs):
        if i < len(self.queryset):
            kwargs['instance'] = self.queryset[i]
        form = super(ItemBaseFormSet, self)._construct_form(i, **kwargs)
        form.parent = self.instance
        return form
