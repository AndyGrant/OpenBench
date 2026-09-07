from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from OpenBench.configuration_import import import_legacy_config, read_legacy_config


class Command(BaseCommand):
    help = 'Import JSON configuration. Credentials remain in Config/credentials.*.'

    def add_arguments(self, parser):
        parser.add_argument('directory', nargs='?', default=settings.BASE_DIR)
        parser.add_argument('--apply', action='store_true', help='Save validated configuration to the database.')
        parser.add_argument('--replace', action='store_true', help='Update site settings and matching entries; retain other entries.')

    def handle(self, *args, **options):
        try:
            bundle = read_legacy_config(options['directory'])
            self.stdout.write('Validated %d engines and %d books.' % (len(bundle['engines']), len(bundle['books'])))
            if options['apply']:
                revision = import_legacy_config(bundle, replace=options['replace'])
                self.stdout.write(self.style.SUCCESS('Published configuration revision %d.' % revision.generation))
            else:
                self.stdout.write('No changes made. Use --apply to import.')
        except (ValidationError, IntegrityError, ValueError, OSError, KeyError, TypeError, AttributeError) as error:
            raise CommandError(str(error)) from error
