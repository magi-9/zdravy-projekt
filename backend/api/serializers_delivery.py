from rest_framework import serializers

from .models import DeliveryBlock, DeliveryRoute, Prevadzka


class DeliveryPrevadzkaSerializer(serializers.ModelSerializer):
    celok = serializers.CharField(source="celok.nazov", read_only=True)
    delivery_route = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryRoute.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Prevadzka
        fields = [
            "id",
            "nazov",
            "report_alias",
            "adresa",
            "celok",
            "delivery_route",
            "delivery_sort_order",
            "delivery_note",
            "is_active",
        ]
        read_only_fields = ["nazov", "adresa", "celok", "is_active"]


class DeliveryRouteSerializer(serializers.ModelSerializer):
    prevadzky = DeliveryPrevadzkaSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryRoute
        fields = [
            "id",
            "block",
            "vydaj",
            "name",
            "driver",
            "departure_time",
            "note",
            "sort_order",
            "is_active",
            "prevadzky",
        ]


class DeliveryBlockSerializer(serializers.ModelSerializer):
    routes = DeliveryRouteSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryBlock
        fields = [
            "id",
            "name",
            "sort_order",
            "include_in_main_summary",
            "include_in_extra_summary",
            "is_active",
            "routes",
        ]


class DeliveryLayoutSerializer(serializers.Serializer):
    blocks = DeliveryBlockSerializer(many=True)
    unassigned_prevadzky = DeliveryPrevadzkaSerializer(many=True)
