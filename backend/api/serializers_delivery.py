from rest_framework import serializers

from .models import DeliveryBlock, DeliveryRoute, Prevadzka


class DeliveryPrevadzkaSerializer(serializers.ModelSerializer):
    """Prevádzka s jej trasami pre všetky tri jedlá naraz.

    Raňajky/obed/olovrant majú vlastné trasy (#dashboard-per-meal-routes) —
    namiesto kontextovo prepínaného poľa serializer jednoducho vystavuje
    všetky tri dvojice, frontend si podľa aktívneho tabu jedla vyberie
    `delivery_route_{meal_type}` / `delivery_sort_order_{meal_type}`.
    """

    celok = serializers.CharField(source="celok.nazov", read_only=True)
    delivery_route_breakfast = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryRoute.objects.all(), required=False, allow_null=True
    )
    delivery_route_lunch = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryRoute.objects.all(), required=False, allow_null=True
    )
    delivery_route_olovrant = serializers.PrimaryKeyRelatedField(
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
            "delivery_route_breakfast",
            "delivery_sort_order_breakfast",
            "delivery_route_lunch",
            "delivery_sort_order_lunch",
            "delivery_route_olovrant",
            "delivery_sort_order_olovrant",
            "delivery_note",
            "is_active",
        ]
        read_only_fields = ["nazov", "adresa", "celok", "is_active"]

    def validate(self, attrs):
        for meal_type in ("breakfast", "lunch", "olovrant"):
            field_name = f"delivery_route_{meal_type}"
            route = attrs.get(field_name)
            if route is not None and route.block.meal_type != meal_type:
                raise serializers.ValidationError(
                    {
                        field_name: (
                            f"Trasa patrí k jedlu {route.block.get_meal_type_display()}, "
                            f"nie k jedlu {meal_type}."
                        )
                    }
                )
        return attrs


class DeliveryRouteSerializer(serializers.ModelSerializer):
    prevadzky = serializers.SerializerMethodField()

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

    def get_prevadzky(self, route: DeliveryRoute) -> list:
        meal_type = route.block.meal_type
        prevadzky = getattr(route, f"prevadzky_{meal_type}").order_by(
            f"delivery_sort_order_{meal_type}", "sort_order", "nazov"
        )
        return DeliveryPrevadzkaSerializer(prevadzky, many=True).data

    def validate(self, attrs):
        block = attrs.get("block")
        if (
            block is not None
            and self.instance is not None
            and block.meal_type != self.instance.block.meal_type
        ):
            raise serializers.ValidationError(
                {"block": "Trasu nemožno presunúť medzi rôznymi jedlami."}
            )
        return attrs


class DeliveryBlockSerializer(serializers.ModelSerializer):
    routes = DeliveryRouteSerializer(many=True, read_only=True)

    class Meta:
        model = DeliveryBlock
        fields = [
            "id",
            "meal_type",
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
