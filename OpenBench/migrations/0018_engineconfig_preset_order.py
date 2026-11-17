from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0017_network_ob_compressed'),
    ]

    operations = [
        migrations.AddField(
            model_name='engineconfig',
            name='preset_order',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
