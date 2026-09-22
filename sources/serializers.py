from rest_framework import serializers

MAX_SMS_BATCH_SIZE = 200


class SMSMessageSerializer(serializers.Serializer):
    body = serializers.CharField(allow_blank=False, trim_whitespace=False)
    sender = serializers.CharField(required=False, allow_blank=True, default='')
    # Optional client-supplied id (e.g. Android's on-device SMS row id) for
    # dedup; if omitted, the view derives one from (sender, body) so the same
    # message synced twice doesn't create two SourceMessage rows.
    external_id = serializers.CharField(required=False, allow_blank=True, default='')


class SMSSyncRequestSerializer(serializers.Serializer):
    messages = SMSMessageSerializer(many=True)

    def validate_messages(self, value):
        if not value:
            raise serializers.ValidationError('messages must not be empty.')
        if len(value) > MAX_SMS_BATCH_SIZE:
            raise serializers.ValidationError(
                f'A single sync batch is limited to {MAX_SMS_BATCH_SIZE} messages.'
            )
        return value
