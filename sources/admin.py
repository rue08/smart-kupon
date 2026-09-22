from django.contrib import admin

from .models import GmailCredential, SourceMessage

admin.site.register(SourceMessage)


@admin.register(GmailCredential)
class GmailCredentialAdmin(admin.ModelAdmin):
    list_display = ['user', 'last_synced_at', 'connected_at']
    readonly_fields = ['access_token_encrypted', 'refresh_token_encrypted']
