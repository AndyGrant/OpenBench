from django.contrib import admin
from EtherBench.models import LogEvent, Engine, Machine, Results, Test

admin.site.register(LogEvent)
admin.site.register(Engine)
admin.site.register(Machine)
admin.site.register(Results)
admin.site.register(Test)
