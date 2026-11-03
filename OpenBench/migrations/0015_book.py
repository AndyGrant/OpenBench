# Books used to be configured with a Books/<name>.json file for each one, all
# of which had to be listed out in Config/config.json. They now live in the
# database instead, so the existing corpus is seeded here, which allows all of
# those .json files to be deleted from the repository.

from django.db import migrations, models

SOURCE = 'https://raw.githubusercontent.com/AndyGrant/openbench-books/master/%s.zip'

BOOKS = [
    ( '2moves_v1.epd'          , '7bec98239836f219dc41944a768c0506abed950aaec48da69a0782643e90f237' ),
    ( '3moves_FRC.epd'         , '6bf81e1ada6a3306bbc8356f7bca1e2984a2828d658799992d5443b7179c934d' ),
    ( '4moves_noob.epd'        , '4be746a91e3f8af0c9344b1e72d611e9fcfe486843867a55760970a4896f284d' ),
    ( '8moves_v3.epd'          , '1f055af431656f09ee6a09d2448e0b876125f78bb7b404fca2031c403a1541e5' ),
    ( 'DFRC.epd'               , '648c447ef40614a44d13b78911e81470d8ddb0d3b2711c1b180e990871f5db4f' ),
    ( 'DFRC_4852_v1.epd'       , '781a754f362827144d3044ae6384d5c7a3d0e84dd51d8d469539a9132add377a' ),
    ( 'Endgames.epd'           , '71c7477ca8c8fb097bb565794d8b5ed8754532f8fb499e9d8b1d397692302a6a' ),
    ( 'Pohl.epd'               , 'b3e64e0dab84cf451a9ac7ef031f5a2bbcf16c7e21be95298fb03cbf021f5466' ),
    ( 'Pohl.pgn'               , 'aaa7559c5d94e592fe5cca3586cb099d8fc5f13428d4ce84afc4b97811241c7e' ),
    ( 'UHO_4060_v2.epd'        , '36f2ec751ab78def6be1307430cbe2cd2ba65ade8d2aaae8f10e3df7d0ea83e1' ),
    ( 'UHO_4060_vB.epd'        , '68c58a5f6a5e068a30376efa19a6bcd78f8ec8bb67ad984dd8d156abfa81de96' ),
    ( 'UHO_4060_vT.epd'        , 'f5da53b91b85f5ddc72c352522a8056ab8bbf0058b67d799c4ca96effd5d5f26' ),
    ( 'UHO_Lichess_4852_v1.epd', '7a7f6470615a69c6cf23d565417701d38732876f480af90d67b42abade35644a' ),
    ( 'dfrc_pawnocchio.epd'    , 'b2111ba99bdca93d4b1d3e808817bcd05ded8d8963a344d3509e79e2120edc8d' ),
    ( 'dfrc_vine_datagen.epd'  , 'e80233fb7ee598b5ae392127c2ee119c98b12b2c5cd1a1f7406c702632c467f2' ),
    ( 'endgames_cdb95105.epd'  , '1c478ddc2758714a25aeb3f8b1f8410466ba4b8a269ee76f96629a9327591fb8' ),
    ( 'fortresses_150_250.epd' , '41243800c6f80c6c167066e1eee5415a32c1bd17b4cace2596ce8dc9b26844b9' ),
    ( 'fortresses_torch.epd'   , '47ed72c0249d79341374fbb0337fa33a8481cd3262f482827002050e9a0d49bb' ),
]

def create_books(apps, schema_editor):

    Book = apps.get_model('OpenBench', 'Book')

    for name, sha in BOOKS:
        Book.objects.get_or_create(name=name, defaults={ 'source' : SOURCE % (name), 'sha' : sha })

class Migration(migrations.Migration):

    dependencies = [
        ('OpenBench', '0014_profile_superuser'),
    ]

    operations = [
        migrations.CreateModel(
            name='Book',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32, unique=True)),
                ('source', models.CharField(max_length=1024)),
                ('sha', models.CharField(max_length=64)),
                ('enabled', models.BooleanField(default=True)),
            ],
        ),
        migrations.RunPython(create_books, migrations.RunPython.noop),
    ]
