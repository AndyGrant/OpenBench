#!/usr/bin/env python3

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                           #
#   OpenBench is a chess engine testing framework by Andrew Grant.          #
#   <https://github.com/AndyGrant/OpenBench>  <andrew@grantnet.us>          #
#                                                                           #
#   OpenBench is free software: you can redistribute it and/or modify       #
#   it under the terms of the GNU General Public License as published by    #
#   the Free Software Foundation, either version 3 of the License, or       #
#   (at your option) any later version.                                     #
#                                                                           #
#   OpenBench is distributed in the hope that it will be useful,            #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of          #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           #
#   GNU General Public License for more details.                            #
#                                                                           #
#   You should have received a copy of the GNU General Public License       #
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.   #
#                                                                           #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import argparse
import getpass
import os
import sys

# Django must be able to find the project
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OpenSite.settings')

import django
django.setup()

from django.contrib.auth.models import User
from OpenBench.models import Profile

def prompt_password():

    password1 = getpass.getpass('Password: ')
    password2 = getpass.getpass('Password (again): ')

    if password1 != password2:
        sys.exit('Passwords do not match')

    return password1

if __name__ == '__main__':

    p = argparse.ArgumentParser(description='Create a Django User and OpenBench Profile')
    p.add_argument('--username', required=True)
    p.add_argument('--email', required=True)
    p.add_argument('--password', help='Prompted for, twice, if not provided')
    p.add_argument('--enabled', action='store_true', help='Set Profile.enabled')
    p.add_argument('--approver', action='store_true', help='Set Profile.approver')
    p.add_argument('--superuser', action='store_true', help='Set is_superuser and is_staff on the Django User')
    args = p.parse_args()

    # Same restrictions as the registration page
    if not args.username.isalnum():
        sys.exit('Alpha-numeric usernames Only')

    if User.objects.filter(username=args.username).exists():
        sys.exit('That username is already taken')

    password = args.password if args.password else prompt_password()
    if not password:
        sys.exit('Password may not be empty')

    user = User.objects.create_user(args.username, args.email, password)
    Profile.objects.create(user=user, enabled=args.enabled, approver=args.approver)

    if args.superuser:
        user.is_superuser = True
        user.is_staff     = True
        user.save()

    print('Created user %s (enabled=%s, approver=%s, superuser=%s)' % (
        args.username, args.enabled, args.approver, args.superuser))
