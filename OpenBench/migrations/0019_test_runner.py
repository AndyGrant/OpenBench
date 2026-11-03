# Which runner played a test's games, for nyayo, which fixes it for a match (settings.runner). Every test
# made before the fastchess worker was played by cutechess-ob and stays so; a test made now is fastchess.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0018_elephant_engine'),
    ]

    operations = [
        migrations.AddField(
            model_name='test',
            name='runner',
            field=models.CharField(default='cutechess-ob', max_length=16),
        ),
        migrations.AlterField(
            model_name='test',
            name='runner',
            field=models.CharField(default='fastchess', max_length=16),
        ),
    ]
