from django.http.response import Http404

from piston.data_processor import MultipleDataProcessorMixin, ResourceProcessorMixin, DataProcessor, data_postprocessors
from piston.resource import BaseModelResource
from piston.exception import DataInvalidException, RestException

from is_core.utils.models import get_model_field_by_name

from flexibee_backend.models.fields import ItemsField


@data_postprocessors.register(BaseModelResource)
class ReverseMultipleDataPreprocessor(MultipleDataProcessorMixin, ResourceProcessorMixin, DataProcessor):

    def _create_and_return_new_object_pk_list(self, data, model, created_via_inst):
        errors = []
        result = []
        i = 0
        for obj_data in data:
            try:
                obj_data['_parent'] = created_via_inst
                result.append(self._create_or_update_related_object(obj_data, model))
            except DataInvalidException as ex:
                rel_obj_errors = ex.errors
                rel_obj_errors['_index'] = i
                errors.append(rel_obj_errors)
            except TypeError:
                errors.append({'error': _('Data must be object'), '_index':i})
            i += 1

        if errors:
            raise DataInvalidException(errors)
        return result

    def _delete_reverse_object(self, obj_data, model):
        resource = self._get_resource(model)
        if resource:
            try:
                resource._delete(self._flat_object_to_pk(resource.pk_field_name, obj_data), self.via,
                                 parent_obj=self.inst)
            except (DataInvalidException, RestException) as ex:
                raise DataInvalidException(ex.errors)
            except Http404:
                raise DataInvalidException({'error': _('Object does not exist')})

    def _create_or_update_reverse_related_objects_set(self, data, key, data_item, field):
        resource = self._get_resource(field.item_class)

        if isinstance(data, (tuple, list)):
            try:
                new_object_pks = self._create_and_return_new_object_pk_list(data, field.item_class, self.inst)
                # This is not optimal solution but is the most universal
                self._delete_reverse_objects(
                    set([obj.pk for obj in resource._get_queryset(self.inst).all()]).difference(set(new_object_pks)),
                    field.item_class)
            except DataInvalidException as ex:
                self._append_errors(key, 'set', ex.errors)
        else:
            self._append_errors(key, 'set', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_reverse_related_objects_remove(self, data, key, data_item, field):
        if isinstance(data, (tuple, list)):
            try:
                self._delete_reverse_objects(data, field.item_class)
            except DataInvalidException as ex:
                self._append_errors(key, 'remove', ex.errors)
        else:
            self._append_errors(key, 'remove', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_reverse_related_objects_add(self, data, key, data_item, field):
        if isinstance(data, (tuple, list)):
            try:
                self._create_and_return_new_object_pk_list(data, field.item_class, self.inst)
            except DataInvalidException as ex:
                self._append_errors(key, 'add', ex.errors)
        else:
            self._append_errors(key, 'add', self.INVALID_COLLECTION_EXCEPTION)

    def _create_or_update_reverse_related_objects(self, data, key, data_item, field):
        resource = self._get_resource(field.item_class)
        if resource:
            if 'set' in data_item:
                self._create_or_update_reverse_related_objects_set(data_item.get('set'), key, data_item, field)
            else:
                if 'remove' in data_item:
                    self._create_or_update_reverse_related_objects_remove(data_item.get('remove'), key,
                                                                          data_item, field)
                if 'add' in data_item:
                    self._create_or_update_reverse_related_objects_add(data_item.get('add'), key,
                                                                       data_item, field)

    def _process_field(self, data, files, key, data_item):
        model_field = get_model_field_by_name(self.model, key)
        if (isinstance(model_field, ItemsField) and isinstance(data_item, dict)
            and set(data_item.keys()).union({'set', 'add', 'remove'})):
            self._create_or_update_reverse_related_objects(data, key, data_item, model_field)
