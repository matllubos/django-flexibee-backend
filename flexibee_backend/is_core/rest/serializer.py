from piston.serializer import Serializer, register, ModelSerializer

from flexibee_backend.models.fields import ItemsManager
from flexibee_backend.models import FlexibeeItem


@register
class FlexibeeItemsManagerSerializer(Serializer):

    def _serialize_to_dict(self, request, manager, format, **kwargs):
        out = []
        for obj in manager.all():
            out.append(self.serialize_chain(request, obj, format, **kwargs))

        return out

    def _can_serialize(self, thing):
        return isinstance(thing, ItemsManager)


@register
class ItemSerializer(ModelSerializer):

    def _serialize_fields(self, request, obj, format, fields, **kwargs):
        resource_method_fields = self._get_resource_method_fields(self._get_model_resource(request, obj), fields)

        out = dict()
        for field in fields:
            subkwargs = self._copy_kwargs(kwargs)
            field = self._get_field_name(field, subkwargs)

            if field in resource_method_fields:
                out[field] = self._serialize_method(resource_method_fields[field], request, obj, format, **subkwargs)
            else:
                out[field] = self.serialize_chain(request, self._get_value(obj, field), format)

        return out

    def _get_value(self, obj, field):
        return getattr(obj, field)

    def _can_serialize(self, thing):
        return isinstance(thing, FlexibeeItem)
